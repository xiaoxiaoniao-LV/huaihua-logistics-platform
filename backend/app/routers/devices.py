"""设备管理：注册、查询、绑定资源、上下线、遥测历史、批量导入与固件 OTA。

设备与资源是多对一关系：一个资源（冷链箱/仓库）可挂多个传感器，
设备表通过 resource_id 关联；resource_id=0 表示尚未绑定。
"""
import csv
import hashlib
import io
import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import mqtt_client
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import IoTData, IoTDevice, OTABatch, OTATask, Resource, User
from ..schemas.device import (
    DeviceCreate, DeviceOut, DeviceUpdate,
    ImportErrorItem, ImportResult, OTABatchOut, OTAReport, OTARequest,
    OTARollbackRequest, OTATaskOut,
)
from ..services.ota_signing import verify_manifest
from .iot import _require_device_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])

_MAX_IMPORT_ROWS = 500

# OTA 版本目录名 / 分发文件名白名单：只允许安全字符，防止路径穿越
_FW_VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,19}$")
_FW_FILE_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}\.py$")
# 节点专属配置与 MicroPython 启动脚本永不参与分发（否则会覆盖节点身份/引脚配置）
_FW_EXCLUDED_FILES = {"config.py", "boot.py"}


def _fw_version_dir(version: str) -> Path:
    """把版本号解析为固件仓库下的版本目录，并阻止越出仓库根目录。"""
    if not _FW_VERSION_RE.match(version or ""):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "版本号格式不合法")
    root = Path(settings.fw_repo_dir).resolve()
    folder = (root / version).resolve()
    if folder.parent != root or not folder.is_dir():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"固件版本 {version} 不存在")
    return folder


def _ensure_can_manage(current: User, dev: IoTDevice, db: Session) -> None:
    """管理员可管理全部设备；普通用户只能管理自己资源上绑定的设备。"""
    if current.role == "admin":
        return
    if dev.resource_id:
        res = db.get(Resource, dev.resource_id)
        if res is not None and res.user_id == current.id:
            return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "无权管理该设备")


def _last_point(db: Session, device_id: int) -> IoTData | None:
    return (
        db.query(IoTData)
        .filter(IoTData.device_id == device_id)
        .order_by(IoTData.recorded_at.desc())
        .first()
    )


def _to_out(db: Session, dev: IoTDevice) -> DeviceOut:
    resource = db.get(Resource, dev.resource_id) if dev.resource_id else None
    last = _last_point(db, dev.id)
    return DeviceOut(
        id=dev.id,
        device_code=dev.device_code,
        device_type=dev.device_type,
        resource_id=dev.resource_id or 0,
        status=dev.status or "offline",
        firmware_version=dev.firmware_version or "1.0.0",
        resource_name=resource.name if resource else None,
        last_seen=last.recorded_at if last else None,
        last_temperature=last.temperature if last else None,
        last_humidity=last.humidity if last else None,
    )


@router.get("", response_model=list[DeviceOut])
def list_devices(
    resource_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    q = db.query(IoTDevice)
    if resource_id is not None:
        q = q.filter(IoTDevice.resource_id == resource_id)
    if status_filter:
        q = q.filter(IoTDevice.status == status_filter)
    return [_to_out(db, d) for d in q.order_by(IoTDevice.id).all()]


@router.post("", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
def register_device(
    data: DeviceCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if db.query(IoTDevice).filter(IoTDevice.device_code == data.device_code).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "设备编码已存在")
    if data.resource_id:
        if db.get(Resource, data.resource_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "要绑定的资源不存在")

    dev = IoTDevice(
        device_code=data.device_code,
        device_type=data.device_type,
        resource_id=data.resource_id or 0,
        status="offline",
    )
    db.add(dev)
    db.commit()
    db.refresh(dev)
    return _to_out(db, dev)


@router.put("/{device_id}", response_model=DeviceOut)
def update_device(
    device_id: int,
    data: DeviceUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dev = db.get(IoTDevice, device_id)
    if dev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "设备不存在")
    _ensure_can_manage(current, dev, db)

    payload = data.model_dump(exclude_unset=True)
    if "resource_id" in payload and payload["resource_id"]:
        if db.get(Resource, payload["resource_id"]) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "要绑定的资源不存在")
    if "status" in payload and payload["status"] not in ("online", "offline"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "状态只能是 online / offline")

    for key, value in payload.items():
        setattr(dev, key, value)
    db.commit()
    db.refresh(dev)
    return _to_out(db, dev)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(
    device_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dev = db.get(IoTDevice, device_id)
    if dev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "设备不存在")
    _ensure_can_manage(current, dev, db)
    db.delete(dev)
    db.commit()


@router.get("/{device_id}/telemetry")
def device_telemetry(
    device_id: int,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    dev = db.get(IoTDevice, device_id)
    if dev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "设备不存在")
    rows = (
        db.query(IoTData)
        .filter(IoTData.device_id == device_id)
        .order_by(IoTData.recorded_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "device_code": dev.device_code,
        "resource_id": dev.resource_id,
        "count": len(rows),
        "data": [
            {
                "temperature": r.temperature,
                "humidity": r.humidity,
                "longitude": r.longitude,
                "latitude": r.latitude,
                "recorded_at": r.recorded_at.isoformat(),
            }
            for r in rows
        ],
    }


@router.post("/auto-bind")
def auto_bind(
    current: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """把尚未绑定的设备按顺序绑定到可用冷链箱资源上（演示/初始化用）。"""
    unbound = (
        db.query(IoTDevice)
        .filter(IoTDevice.resource_id == 0)
        .order_by(IoTDevice.id)
        .all()
    )
    if not unbound:
        return {"bound": 0, "detail": "没有待绑定的设备"}

    taken = {
        d.resource_id
        for d in db.query(IoTDevice).filter(IoTDevice.resource_id != 0).all()
    }
    free_resources = [
        r
        for r in db.query(Resource)
        .filter(Resource.type == "cold_box")
        .order_by(Resource.id)
        .all()
        if r.id not in taken
    ]

    bound = 0
    for dev, res in zip(unbound, free_resources):
        dev.resource_id = res.id
        bound += 1
    db.commit()
    logger.info("[devices] auto-bind 完成，绑定 %d 台设备", bound)
    return {"bound": bound, "detail": f"已绑定 {bound} 台设备"}


# ---------------- 批量导入 ----------------

@router.post("/import", response_model=ImportResult)
async def import_devices(
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """按 CSV 批量注册设备。

    表头：device_code,device_type,resource_id,firmware_version
    仅 device_code 必填；编码重复的设备跳过，资源不存在等错误逐行返回。
    """
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件需为 UTF-8 编码的 CSV")

    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CSV 至少需要表头和一行数据")
    if len(lines) - 1 > _MAX_IMPORT_ROWS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"单次最多导入 {_MAX_IMPORT_ROWS} 行"
        )

    reader = csv.DictReader(io.StringIO(text))
    header = {(name or "").strip().lower(): name for name in (reader.fieldnames or [])}
    if "device_code" not in header:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "CSV 缺少 device_code 列，示例表头：device_code,device_type,resource_id,firmware_version",
        )

    def cell(row: dict, key: str) -> str:
        return (row.get(header[key]) or "").strip() if key in header else ""

    created = skipped = 0
    errors: list[ImportErrorItem] = []
    pending: list[IoTDevice] = []
    seen: set[str] = set()
    existing = {d.device_code for d in db.query(IoTDevice.device_code).all()}

    for offset, row in enumerate(reader, start=2):
        code = cell(row, "device_code")
        if not code:
            errors.append(ImportErrorItem(row=offset, reason="device_code 不能为空"))
            continue
        if len(code) > 50:
            errors.append(ImportErrorItem(row=offset, device_code=code, reason="device_code 超过 50 字符"))
            continue
        if code in seen:
            errors.append(ImportErrorItem(row=offset, device_code=code, reason="文件内编码重复"))
            continue
        seen.add(code)
        if code in existing:
            skipped += 1
            continue

        raw_resource = cell(row, "resource_id")
        resource_id = 0
        if raw_resource:
            try:
                resource_id = int(raw_resource)
            except ValueError:
                errors.append(ImportErrorItem(row=offset, device_code=code, reason="resource_id 必须是整数"))
                continue
            if resource_id and db.get(Resource, resource_id) is None:
                errors.append(ImportErrorItem(row=offset, device_code=code, reason=f"资源 {resource_id} 不存在"))
                continue

        firmware = cell(row, "firmware_version") or "1.0.0"
        if len(firmware) > 20:
            errors.append(ImportErrorItem(row=offset, device_code=code, reason="firmware_version 超过 20 字符"))
            continue

        pending.append(IoTDevice(
            device_code=code,
            device_type=cell(row, "device_type")[:30] or None,
            resource_id=resource_id,
            status="offline",
            firmware_version=firmware,
        ))

    if pending:
        db.add_all(pending)
        db.commit()
        created = len(pending)

    logger.info(
        "[devices] 批量导入：新增 %d，跳过 %d，失败 %d（操作人 %s）",
        created, skipped, len(errors), admin.username,
    )
    return ImportResult(created=created, skipped=skipped, failed=len(errors), errors=errors)


# ---------------- 固件 OTA ----------------

def _task_out(task: OTATask, device_code: str | None = None) -> OTATaskOut:
    return OTATaskOut(
        id=task.id, device_id=task.device_id, device_code=device_code,
        from_version=task.from_version, target_version=task.target_version,
        status=task.status, message=task.message,
        batch_id=task.batch_id, stage=task.stage,
        created_at=task.created_at, finished_at=task.finished_at,
    )


def _scope_devices(
    db: Session, space_id: int | None, device_ids: list[int] | None
) -> list[IoTDevice]:
    q = db.query(IoTDevice)
    if device_ids:
        q = q.filter(IoTDevice.id.in_(device_ids))
    if space_id:
        q = q.filter(IoTDevice.space_id == space_id)
    return q.order_by(IoTDevice.id).all()


def _sample_devices(batch_id: str, devices: list[IoTDevice], percent: int) -> list[IoTDevice]:
    """按批次+设备号确定性抽样，保证同一批次反复续发时命中集合稳定。"""
    if percent >= 100:
        return list(devices)
    picked = [
        dev for dev in devices
        if int(hashlib.sha256(f"{batch_id}:{dev.id}".encode()).hexdigest()[:8], 16) % 100 < percent
    ]
    # 比例过小时至少下发一台，否则灰度完全不可观测
    return picked or devices[:1]


def _dispatch_ota(
    db: Session, devices: list[IoTDevice], target: str, batch_id: str, stage: str
) -> list[tuple[OTATask, IoTDevice]]:
    """创建任务并逐台下发 MQTT 指令；返回 (任务, 设备) 列表。"""
    tasks: list[tuple[OTATask, IoTDevice]] = []
    for dev in devices:
        current = dev.firmware_version or "1.0.0"
        if current == target:
            continue
        task = OTATask(
            device_id=dev.id,
            from_version=current,
            target_version=target,
            status="pending",
            batch_id=batch_id,
            stage=stage,
        )
        db.add(task)
        tasks.append((task, dev))
    if not tasks:
        return []
    db.commit()  # 先落库，避免设备回执早于任务提交

    for task, dev in tasks:
        if mqtt_client.publish(
            f"iot/{dev.device_code}/cmd",
            {"action": "ota", "task_id": task.id, "target_version": target},
        ):
            task.status = "running"
        else:
            # 下发失败直接置 failed，避免 pending 卡死导致批次永远 running
            task.status = "failed"
            task.message = "MQTT 下发失败"
            task.finished_at = datetime.now()
    db.commit()
    return tasks


def _get_batch(db: Session, batch_id: str) -> OTABatch:
    batch = db.get(OTABatch, batch_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "升级批次不存在")
    return batch


def _refresh_batch_status(db: Session, batch_id: str | None) -> None:
    """批次内任务全部结束后收敛批次状态。"""
    if not batch_id:
        return
    rows = dict(
        db.query(OTATask.status, func.count())
        .filter(OTATask.batch_id == batch_id)
        .group_by(OTATask.status)
        .all()
    )
    if rows.get("pending") or rows.get("running"):
        return
    batch = db.get(OTABatch, batch_id)
    if batch is None or batch.status in ("done", "failed", "rolled_back"):
        return
    batch.status = "done" if rows.get("success") else "failed"
    db.commit()


def _batch_out(db: Session, batch: OTABatch) -> OTABatchOut:
    rows = dict(
        db.query(OTATask.status, func.count())
        .filter(OTATask.batch_id == batch.id)
        .group_by(OTATask.status)
        .all()
    )
    pending = rows.get("pending", 0)
    running = rows.get("running", 0)
    success = rows.get("success", 0)
    failed = rows.get("failed", 0)
    return OTABatchOut(
        batch_id=batch.id,
        target_version=batch.target_version,
        stage=batch.stage,
        status=batch.status,
        rollout_percent=batch.rollout_percent,
        rollback_of=batch.rollback_of,
        total=pending + running + success + failed,
        pending=pending,
        running=running,
        success=success,
        failed=failed,
    )


def _batch_scope_devices(db: Session, batch: OTABatch) -> list[IoTDevice]:
    device_ids = json.loads(batch.device_ids) if batch.device_ids else None
    return _scope_devices(db, batch.space_id, device_ids)


@router.post("/ota", response_model=list[OTATaskOut])
def create_ota_job(
    data: OTARequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """批量创建升级任务并通过 MQTT 下发；rollout_percent<100 时进入灰度批次。"""
    target = data.target_version.strip()
    if not target:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "目标版本不能为空")

    devices = _scope_devices(db, data.space_id, data.device_ids)
    if not devices:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "没有符合条件的设备")

    candidates = [d for d in devices if (d.firmware_version or "1.0.0") != target]
    if not candidates:
        return []

    batch_id = uuid.uuid4().hex
    stage = "canary" if data.rollout_percent < 100 else "full"
    picked = _sample_devices(batch_id, candidates, data.rollout_percent)

    batch = OTABatch(
        id=batch_id,
        target_version=target,
        space_id=data.space_id,
        device_ids=json.dumps(data.device_ids) if data.device_ids else None,
        rollout_percent=data.rollout_percent,
        stage=stage,
        status="running",
        created_by=admin.id,
    )
    db.add(batch)
    db.commit()

    tasks = _dispatch_ota(db, picked, target, batch_id, stage)
    if not tasks:
        batch.status = "done"
        db.commit()
        return []

    logger.info(
        "[devices] OTA 下发：目标版本 %s，批次 %s（%s %d%%），任务 %d 个（操作人 %s）",
        target, batch_id, stage, data.rollout_percent, len(tasks), admin.username,
    )
    return [_task_out(t, dev.device_code) for t, dev in tasks]


@router.get("/ota", response_model=list[OTATaskOut])
def list_ota_tasks(
    limit: int = Query(20, ge=1, le=200),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """最近升级任务；管理员看全部，普通用户只看自己资源上的设备。"""
    q = db.query(OTATask, IoTDevice).join(IoTDevice, OTATask.device_id == IoTDevice.id)
    if current.role != "admin":
        owned = {r.id for r in db.query(Resource.id).filter(Resource.user_id == current.id).all()}
        if not owned:
            return []
        q = q.filter(IoTDevice.resource_id.in_(owned))
    rows = q.order_by(OTATask.id.desc()).limit(limit).all()
    return [_task_out(t, dev.device_code) for t, dev in rows]


@router.get("/ota/manifest/{version}", dependencies=[Depends(_require_device_token)])
def get_ota_manifest(version: str):
    """设备拉取升级清单（文件级 OTA 第一步）。

    清单由 `iot/tools/make_release.py` 生成：
    {"version": "3.1.0", "files": [{"name": "main.py", "size": 123, "sha256": "..."}]}
    节点专属的 config.py / boot.py 始终从清单中剔除。
    """
    folder = _fw_version_dir(version)
    path = folder / "manifest.json"
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "该版本缺少 manifest.json")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.error("[devices] 固件 manifest 解析失败 %s: %s", path, e)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "manifest.json 无法解析")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "manifest.json 结构不合法")

    manifest["version"] = manifest.get("version") or version

    # 签名校验：配置了公钥就必须通过；未配置公钥时按 ota_require_signature 决定是否放行
    if settings.ota_public_key:
        ok, reason = verify_manifest(manifest)
        if not ok:
            logger.error("[devices] 固件 %s 清单验签失败：%s", version, reason)
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"固件清单验签失败：{reason}")
    elif settings.ota_require_signature:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "服务端未配置 OTA_PUBLIC_KEY，无法校验固件清单签名",
        )

    # 签名清单不得夹带节点专属文件，否则验签通过也无法安全下发
    excluded_in_manifest = [
        str(item.get("name"))
        for item in manifest["files"]
        if isinstance(item, dict) and str(item.get("name", "")) in _FW_EXCLUDED_FILES
    ]
    if excluded_in_manifest and manifest.get("signature"):
        logger.error("[devices] 固件 %s 签名清单包含禁止分发文件：%s", version, excluded_in_manifest)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "签名清单包含禁止分发文件")

    manifest["files"] = [
        item
        for item in manifest["files"]
        if isinstance(item, dict) and str(item.get("name", "")) not in _FW_EXCLUDED_FILES
    ]
    return manifest


@router.get("/ota/file/{version}/{filename}", dependencies=[Depends(_require_device_token)])
def download_ota_file(version: str, filename: str):
    """设备下载单个固件文件（文件级 OTA 第二步），只允许 .py 且不接受 config.py。"""
    folder = _fw_version_dir(version)
    if not _FW_FILE_RE.match(filename) or filename in _FW_EXCLUDED_FILES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件名不合法")
    path = (folder / filename).resolve()
    if path.parent != folder or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "固件文件不存在")
    return FileResponse(path, media_type="text/x-python", filename=filename)


@router.post("/ota/report", dependencies=[Depends(_require_device_token)])
def report_ota(data: OTAReport, db: Session = Depends(get_db)):
    """设备上报升级结果：成功后更新设备固件版本。"""
    dev = db.query(IoTDevice).filter(IoTDevice.device_code == data.device_code).first()
    if dev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "设备不存在")
    task = (
        db.query(OTATask)
        .filter(OTATask.device_id == dev.id, OTATask.target_version == data.target_version)
        .order_by(OTATask.id.desc())
        .first()
    )
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "没有对应的升级任务")

    task.status = "success" if data.success else "failed"
    task.message = (data.message or "")[:255] or None
    task.finished_at = datetime.now()
    if data.success:
        dev.firmware_version = data.target_version
    db.commit()
    _refresh_batch_status(db, task.batch_id)
    logger.info(
        "[devices] OTA 回执：%s %s → %s，结果 %s",
        dev.device_code, task.from_version, task.target_version, task.status,
    )
    return {
        "task_id": task.id,
        "status": task.status,
        "firmware_version": dev.firmware_version,
    }


@router.get("/ota/batch/{batch_id}", response_model=OTABatchOut)
def get_ota_batch(
    batch_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """查看灰度/全量升级批次的任务统计。"""
    return _batch_out(db, _get_batch(db, batch_id))


@router.post("/ota/batch/{batch_id}/promote", response_model=OTABatchOut)
def promote_ota_batch(
    batch_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """灰度批次续发为全量：向范围内尚未升级的设备补发任务。"""
    batch = _get_batch(db, batch_id)
    if batch.stage == "rollback":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "回滚批次不能续发")

    counts = dict(
        db.query(OTATask.status, func.count())
        .filter(OTATask.batch_id == batch_id)
        .group_by(OTATask.status)
        .all()
    )
    if counts.get("failed"):
        raise HTTPException(status.HTTP_409_CONFLICT, "批次存在失败任务，请先排查或回滚")

    busy = {
        t.device_id
        for t in db.query(OTATask)
        .filter(OTATask.batch_id == batch_id, OTATask.status.in_(("pending", "running")))
        .all()
    }
    devices = [d for d in _batch_scope_devices(db, batch) if d.id not in busy]
    candidates = [d for d in devices if (d.firmware_version or "1.0.0") != batch.target_version]

    batch.stage = "full"
    batch.rollout_percent = 100
    batch.status = "running"
    db.commit()

    tasks = _dispatch_ota(db, candidates, batch.target_version, batch.id, "full")
    if not tasks:
        _refresh_batch_status(db, batch.id)
    logger.info(
        "[devices] OTA 批次续发：%s → %s，新增任务 %d 个（操作人 %s）",
        batch_id, batch.target_version, len(tasks), admin.username,
    )
    return _batch_out(db, batch)


@router.post("/ota/batch/{batch_id}/rollback", response_model=OTABatchOut)
def rollback_ota_batch(
    batch_id: str,
    data: OTARollbackRequest | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """回滚批次：新建回滚批次，把范围内设备退回到指定/原版本。"""
    batch = _get_batch(db, batch_id)
    if batch.status == "rolled_back":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该批次已回滚")

    target = ((data.target_version if data else None) or "").strip() or None
    if target is None:
        # 仅当批次内所有任务的 from_version 一致时才自动推定；版本不一致时要求显式指定，
        # 避免按众数推定把部分设备退回错误基线。
        rows = (
            db.query(OTATask.from_version)
            .filter(OTATask.batch_id == batch_id, OTATask.from_version.isnot(None))
            .distinct()
            .all()
        )
        versions = [row[0] for row in rows if row[0]]
        if len(versions) == 1:
            target = versions[0]
        else:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "批次内设备原版本不一致，请显式指定 target_version",
            )
    if not target:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "无法确定回滚目标版本，请显式指定")

    devices = _batch_scope_devices(db, batch)
    if not devices:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "批次范围内没有设备")

    batch.status = "rolled_back"
    db.commit()

    rollback_id = uuid.uuid4().hex
    rollback = OTABatch(
        id=rollback_id,
        target_version=target,
        space_id=batch.space_id,
        device_ids=batch.device_ids,
        rollout_percent=100,
        stage="rollback",
        status="running",
        rollback_of=batch.id,
        created_by=admin.id,
    )
    db.add(rollback)
    db.commit()

    tasks = _dispatch_ota(db, devices, target, rollback_id, "rollback")
    if not tasks:
        rollback.status = "done"
        db.commit()
    logger.warning(
        "[devices] OTA 回滚：%s → %s，回滚批次 %s，任务 %d 个（操作人 %s）",
        batch.target_version, target, rollback_id, len(tasks), admin.username,
    )
    return _batch_out(db, rollback)
