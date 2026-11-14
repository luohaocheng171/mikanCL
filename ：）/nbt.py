"""最小 NBT（Named Binary Tag）读写实现，不依赖第三方库。

支持 level.dat / playerdata 等 .dat 存档文件的解析与写回：
- TAG_Compound 用 dict 表示，TAG_List 用 list 表示
- 字符串使用 UTF-8 + 2 字节长度前缀
- 定长类型用 struct 按大端读写
- gzip 依据文件头 0x1f 0x8b 自动识别，写出 .dat 默认压缩
"""

from __future__ import annotations

import gzip
import struct
from pathlib import Path
from typing import Any

TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12

TAG_NAMES = {
    TAG_END: "TAG_End",
    TAG_BYTE: "TAG_Byte",
    TAG_SHORT: "TAG_Short",
    TAG_INT: "TAG_Int",
    TAG_LONG: "TAG_Long",
    TAG_FLOAT: "TAG_Float",
    TAG_DOUBLE: "TAG_Double",
    TAG_BYTE_ARRAY: "TAG_Byte_Array",
    TAG_STRING: "TAG_String",
    TAG_LIST: "TAG_List",
    TAG_COMPOUND: "TAG_Compound",
    TAG_INT_ARRAY: "TAG_Int_Array",
    TAG_LONG_ARRAY: "TAG_Long_Array",
}

# 简单叶子类型：标签值就是 Python 标量
_SCALAR_FORMATS = {
    TAG_BYTE: ">b",
    TAG_SHORT: ">h",
    TAG_INT: ">i",
    TAG_LONG: ">q",
    TAG_FLOAT: ">f",
    TAG_DOUBLE: ">d",
}


class NBTError(Exception):
    """NBT 数据损坏或结构不支持时抛出。"""


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def read(self, count: int) -> bytes:
        if count < 0 or self.pos + count > len(self.data):
            raise NBTError("NBT 数据不完整（读取越界）")
        chunk = self.data[self.pos : self.pos + count]
        self.pos += count
        return chunk

    def unpack(self, fmt: str) -> Any:
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, self.read(size))[0]

    def read_string(self) -> str:
        length = self.unpack(">H")
        raw = self.read(length)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise NBTError(f"NBT 字符串不是合法 UTF-8：{exc}") from exc


class _Writer:
    def __init__(self):
        self.parts: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.parts.append(data)

    def pack(self, fmt: str, value: Any) -> None:
        self.parts.append(struct.pack(fmt, value))

    def write_string(self, text: str) -> None:
        raw = text.encode("utf-8")
        if len(raw) > 0xFFFF:
            raise NBTError("NBT 字符串超过 65535 字节，无法写入")
        self.pack(">H", len(raw))
        self.write(raw)

    def payload(self) -> bytes:
        return b"".join(self.parts)


def _infer_tag(value: Any) -> int:
    if isinstance(value, bool):
        return TAG_BYTE
    if isinstance(value, int):
        return TAG_INT
    if isinstance(value, float):
        return TAG_DOUBLE
    if isinstance(value, str):
        return TAG_STRING
    if isinstance(value, dict):
        return TAG_COMPOUND
    if isinstance(value, list):
        return TAG_LIST
    if isinstance(value, (bytes, bytearray)):
        return TAG_BYTE_ARRAY
    raise NBTError(f"无法推断 NBT 类型：{type(value)!r}")


def _read_payload(reader: _Reader, tag: int) -> Any:
    if tag == TAG_BYTE:
        return reader.unpack(">b")
    if tag == TAG_SHORT:
        return reader.unpack(">h")
    if tag == TAG_INT:
        return reader.unpack(">i")
    if tag == TAG_LONG:
        return reader.unpack(">q")
    if tag == TAG_FLOAT:
        return reader.unpack(">f")
    if tag == TAG_DOUBLE:
        return reader.unpack(">d")
    if tag == TAG_BYTE_ARRAY:
        length = reader.unpack(">i")
        return bytearray(reader.read(length))
    if tag == TAG_STRING:
        return reader.read_string()
    if tag == TAG_INT_ARRAY:
        length = reader.unpack(">i")
        return [reader.unpack(">i") for _ in range(max(0, length))]
    if tag == TAG_LONG_ARRAY:
        length = reader.unpack(">i")
        return [reader.unpack(">q") for _ in range(max(0, length))]
    if tag == TAG_LIST:
        element_tag = reader.unpack(">b")
        length = reader.unpack(">i")
        if element_tag == TAG_END:
            return []
        return [_read_payload(reader, element_tag) for _ in range(max(0, length))]
    if tag == TAG_COMPOUND:
        result: dict[str, Any] = {}
        while True:
            child_tag = reader.unpack(">b")
            if child_tag == TAG_END:
                return result
            name = reader.read_string()
            result[name] = _read_payload(reader, child_tag)
    raise NBTError(f"未知的 NBT 标签类型：{tag}")


def _write_payload(writer: _Writer, tag: int, value: Any) -> None:
    if tag in _SCALAR_FORMATS:
        fmt = _SCALAR_FORMATS[tag]
        if tag == TAG_BYTE and isinstance(value, bool):
            value = 1 if value else 0
        writer.pack(fmt, value)
        return
    if tag == TAG_BYTE_ARRAY:
        data = bytes(value)
        writer.pack(">i", len(data))
        writer.write(data)
        return
    if tag == TAG_STRING:
        writer.write_string(str(value))
        return
    if tag == TAG_INT_ARRAY:
        writer.pack(">i", len(value))
        for item in value:
            writer.pack(">i", int(item))
        return
    if tag == TAG_LONG_ARRAY:
        writer.pack(">i", len(value))
        for item in value:
            writer.pack(">q", int(item))
        return
    if tag == TAG_LIST:
        items = list(value)
        element_tag = _infer_tag(items[0]) if items else TAG_END
        writer.pack(">b", element_tag)
        writer.pack(">i", len(items))
        for item in items:
            _write_payload(writer, element_tag, item)
        return
    if tag == TAG_COMPOUND:
        for name, child in value.items():
            if isinstance(child, tuple) and len(child) == 2:
                # 允许显式指定类型：(tag, value)
                child_tag, child_value = child
            else:
                child_tag, child_value = _infer_tag(child), child
            writer.pack(">b", child_tag)
            writer.write_string(str(name))
            _write_payload(writer, child_tag, child_value)
        writer.pack(">b", TAG_END)
        return
    raise NBTError(f"未知的 NBT 标签类型：{tag}")


def _maybe_decompress(data: bytes) -> bytes:
    if data[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(data)
        except (OSError, EOFError) as exc:
            raise NBTError(f"gzip 解压失败：{exc}") from exc
    return data


def parse_nbt(data: bytes) -> tuple[str, dict]:
    """解析 NBT 二进制，返回 (根标签名, 根 Compound dict)。"""
    raw = _maybe_decompress(data)
    reader = _Reader(raw)
    tag = reader.unpack(">b")
    if tag == TAG_END:
        return "", {}
    if tag != TAG_COMPOUND:
        raise NBTError(f"根标签必须是 TAG_Compound，实际为 {TAG_NAMES.get(tag, tag)}")
    root_name = reader.read_string()
    root = _read_payload(reader, TAG_COMPOUND)
    return root_name, root


def write_nbt(root_name: str, root: dict) -> bytes:
    """把根 Compound 写成未压缩的 NBT 二进制。"""
    writer = _Writer()
    writer.pack(">b", TAG_COMPOUND)
    writer.write_string(root_name)
    _write_payload(writer, TAG_COMPOUND, root)
    return writer.payload()


def load_nbt_file(path: Path) -> tuple[str, dict]:
    """读取 .dat 存档文件（自动识别 gzip），返回 (根标签名, 根 Compound)。"""
    data = Path(path).read_bytes()
    return parse_nbt(data)


def save_nbt_file(path: Path, root_name: str, root: dict) -> None:
    """把 NBT 写回文件；.dat 存档默认 gzip 压缩，其余后缀写裸数据。"""
    target = Path(path)
    payload = write_nbt(root_name, root)
    if target.suffix.lower() in (".dat", ".nbt"):
        payload = gzip.compress(payload)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_bytes(payload)
    tmp.replace(target)


# ----------------------------------------------------------------------
# 带类型信息的变体：供 NBT 编辑器使用，保证写回时标签类型不变
# 节点统一表示为 (tag, value)：
#   TAG_Compound -> (TAG_COMPOUND, {name: node})
#   TAG_List     -> (TAG_LIST, (element_tag, [node, ...]))
# ----------------------------------------------------------------------


def _read_typed(reader: _Reader, tag: int) -> tuple[int, Any]:
    if tag == TAG_COMPOUND:
        result: dict[str, tuple[int, Any]] = {}
        while True:
            child_tag = reader.unpack(">b")
            if child_tag == TAG_END:
                return (TAG_COMPOUND, result)
            name = reader.read_string()
            result[name] = _read_typed(reader, child_tag)
    if tag == TAG_LIST:
        element_tag = reader.unpack(">b")
        length = reader.unpack(">i")
        if length < 0:
            raise NBTError("NBT 列表长度非法")
        if element_tag == TAG_END:
            return (TAG_LIST, (TAG_END, []))
        items = [_read_typed(reader, element_tag) for _ in range(length)]
        return (TAG_LIST, (element_tag, items))
    return (tag, _read_payload(reader, tag))


def _write_typed(writer: _Writer, tag: int, value: Any) -> None:
    if tag == TAG_COMPOUND:
        for name, child in value.items():
            child_tag, child_value = child
            writer.pack(">b", child_tag)
            writer.write_string(str(name))
            _write_typed(writer, child_tag, child_value)
        writer.pack(">b", TAG_END)
        return
    if tag == TAG_LIST:
        element_tag, items = value
        writer.pack(">b", element_tag)
        writer.pack(">i", len(items))
        for item_tag, item_value in items:
            _write_typed(writer, item_tag, item_value)
        return
    _write_payload(writer, tag, value)


def parse_nbt_typed(data: bytes) -> tuple[str, tuple[int, Any]]:
    """解析 NBT 并保留每个标签的类型，返回 (根标签名, 根节点)。"""
    raw = _maybe_decompress(data)
    reader = _Reader(raw)
    tag = reader.unpack(">b")
    if tag == TAG_END:
        return "", (TAG_COMPOUND, {})
    if tag != TAG_COMPOUND:
        raise NBTError(f"根标签必须是 TAG_Compound，实际为 {TAG_NAMES.get(tag, tag)}")
    root_name = reader.read_string()
    return root_name, _read_typed(reader, TAG_COMPOUND)


def write_nbt_typed(root_name: str, root_node: tuple[int, Any]) -> bytes:
    """把带类型信息的根节点写成未压缩 NBT 二进制。"""
    if root_node[0] != TAG_COMPOUND:
        raise NBTError("根节点必须是 TAG_Compound")
    writer = _Writer()
    writer.pack(">b", TAG_COMPOUND)
    writer.write_string(root_name)
    _write_typed(writer, TAG_COMPOUND, root_node[1])
    return writer.payload()


def load_nbt_typed_file(path: Path) -> tuple[str, tuple[int, Any]]:
    return parse_nbt_typed(Path(path).read_bytes())


def save_nbt_typed_file(path: Path, root_name: str, root_node: tuple[int, Any]) -> None:
    target = Path(path)
    payload = write_nbt_typed(root_name, root_node)
    if target.suffix.lower() in (".dat", ".nbt"):
        payload = gzip.compress(payload)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_bytes(payload)
    tmp.replace(target)
