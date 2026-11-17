"""设备管理：注册、查询、绑定资源、上下线、遥测历史、批量导入与固件 OTA。

设备与资源是多对一关系：一个资源（冷链箱/仓库）可挂多个传感器，
设备表通过 resource_id 关联；resource_id=0 表示尚未绑定。
"""
import csv
import io
import json
import logging
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import mqtt_client
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import IoTData, IoTDevice, OTATask, Resource, User
from ..schemas.device import (
    DeviceCreate, DeviceOut, DeviceUpdate,
    ImportErrorItem, ImportResult, OTAReport, OTARequest, OTATaskOut,
)
from .iot import _verify_device_token

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

@router.post("/ota", response_model=list[OTATaskOut])
def create_ota_job(
    data: OTARequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """为目标版本低于 target_version 的设备批量创建升级任务，并通过 MQTT 下发指令。"""
    target = data.target_version.strip()
    if not target:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "目标版本不能为空")

    q = db.query(IoTDevice)
    if data.device_ids:
        q = q.filter(IoTDevice.id.in_(data.device_ids))
    devices = q.order_by(IoTDevice.id).all()
    if not devices:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "没有符合条件的设备")

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
    db.commit()

    codes = {d.id: d.device_code for d in devices}
    logger.info(
        "[devices] OTA 下发：目标版本 %s，任务 %d 个（操作人 %s）",
        target, len(tasks), admin.username,
    )
    return [
        OTATaskOut(
            id=t.id, device_id=t.device_id, device_code=codes.get(t.device_id),
            from_version=t.from_version, target_version=t.target_version,
            status=t.status, message=t.message,
            created_at=t.created_at, finished_at=t.finished_at,
        )
        for t, _dev in tasks
    ]


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
    return [
        OTATaskOut(
            id=t.id, device_id=t.device_id, device_code=dev.device_code,
            from_version=t.from_version, target_version=t.target_version,
            status=t.status, message=t.message,
            created_at=t.created_at, finished_at=t.finished_at,
        )
        for t, dev in rows
    ]


@router.get("/ota/manifest/{version}", dependencies=[Depends(_verify_device_token)])
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
    manifest["files"] = [
        item
        for item in manifest["files"]
        if isinstance(item, dict) and str(item.get("name", "")) not in _FW_EXCLUDED_FILES
    ]
    return manifest


@router.get("/ota/file/{version}/{filename}", dependencies=[Depends(_verify_device_token)])
def download_ota_file(version: str, filename: str):
    """设备下载单个固件文件（文件级 OTA 第二步），只允许 .py 且不接受 config.py。"""
    folder = _fw_version_dir(version)
    if not _FW_FILE_RE.match(filename) or filename in _FW_EXCLUDED_FILES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件名不合法")
    path = (folder / filename).resolve()
    if path.parent != folder or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "固件文件不存在")
    return FileResponse(path, media_type="text/x-python", filename=filename)


@router.post("/ota/report", dependencies=[Depends(_verify_device_token)])
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
    logger.info(
        "[devices] OTA 回执：%s %s → %s，结果 %s",
        dev.device_code, task.from_version, task.target_version, task.status,
    )
    return {
        "task_id": task.id,
        "status": task.status,
        "firmware_version": dev.firmware_version,
    }
