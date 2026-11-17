"""数字孪生：点位字典、孪生节点、绑定关系。

- DevicePoint  设备可采集/可控的点位字典（温度、湿度、门磁、电流…）
- TwinNode     三维场景节点（园区/楼栋/库房/货架/设备位），可挂模型与变换
- TwinBinding  孪生节点与设备点位的绑定，决定节点上显示哪条实时状态
"""
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, Integer, JSON, String, UniqueConstraint, func

from ..database import Base


class DevicePoint(Base):
    __tablename__ = "device_points"
    __table_args__ = (UniqueConstraint("device_id", "point_key", name="uq_device_point"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    device_id = Column(BigInteger, nullable=False, index=True)
    point_key = Column(String(50), nullable=False)   # temp_in / hum_in / door / current_a
    name = Column(String(100), nullable=False)
    unit = Column(String(20))
    data_type = Column(String(10), nullable=False, default="number")  # number/text/bool
    precision = Column(Integer, nullable=False, default=1)
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    writable = Column(Boolean, nullable=False, default=False)
    sort = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())


class TwinNode(Base):
    __tablename__ = "twin_nodes"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    node_key = Column(String(80), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    # site / building / room / zone / rack / device
    node_type = Column(String(20), nullable=False, default="room")
    parent_id = Column(BigInteger, nullable=True, index=True)
    space_id = Column(BigInteger, nullable=True, index=True)
    model_ref = Column(String(200))                  # 模型资源标识（glb/gltf）
    transform = Column(JSON, nullable=True)          # {x,y,z,rx,ry,rz,scale}
    sort = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())


class TwinBinding(Base):
    __tablename__ = "twin_bindings"
    __table_args__ = (
        UniqueConstraint("twin_node_id", "device_id", "point_key", name="uq_twin_binding"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    twin_node_id = Column(BigInteger, nullable=False, index=True)
    device_id = Column(BigInteger, nullable=False, index=True)
    point_key = Column(String(50), nullable=False)
    # anchor=定位锚点；status=节点主状态；telemetry=补充指标
    binding_type = Column(String(20), nullable=False, default="telemetry")
    created_at = Column(DateTime, server_default=func.now())
