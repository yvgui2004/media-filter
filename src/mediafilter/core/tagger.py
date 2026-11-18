"""Local video content tagging: ffmpeg frame extraction + YOLOv8 ONNX inference.

Pure Python/NumPy, no Qt — testable without opening the window. The ONNX
runtime import is lazy so the app still starts (and scans) when the AI extra
is not installed.
"""

# numpy is imported defensively below; type checkers treat the fallback as None.
# pyright: reportOptionalMemberAccess=false, reportInvalidTypeForm=false

from __future__ import annotations

import math
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

try:  # optional: the app must still start for users who never use AI tagging
    import numpy as np
except ImportError:  # pragma: no cover - exercised only on minimal installs
    np = None

INPUT_SIZE = 640
PAD_COLOR = 0x727272          # letterbox fill, matches Ultralytics' 114 grey
RAW_FRAME_BYTES = INPUT_SIZE * INPUT_SIZE * 3

# COCO-80 class names, in YOLO output order.
COCO_NAMES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
    "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
    "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush",
]

# English class -> short Chinese tag. Grouped where it helps filtering.
ZH_TAGS = {
    "person": "人物", "bicycle": "自行车", "car": "汽车", "motorcycle": "摩托车",
    "airplane": "飞机", "bus": "公交车", "train": "火车", "truck": "卡车", "boat": "船",
    "traffic light": "红绿灯", "fire hydrant": "消防栓", "stop sign": "停车标志",
    "parking meter": "停车计时器", "bench": "长椅", "bird": "鸟", "cat": "猫", "dog": "狗",
    "horse": "马", "sheep": "羊", "cow": "牛", "elephant": "大象", "bear": "熊",
    "zebra": "斑马", "giraffe": "长颈鹿", "backpack": "背包", "umbrella": "雨伞",
    "handbag": "手提包", "tie": "领带", "suitcase": "行李箱", "frisbee": "飞盘",
    "skis": "滑雪板", "snowboard": "单板", "sports ball": "球", "kite": "风筝",
    "baseball bat": "球棒", "baseball glove": "手套", "skateboard": "滑板",
    "surfboard": "冲浪板", "tennis racket": "球拍", "bottle": "瓶子", "wine glass": "酒杯",
    "cup": "杯子", "fork": "叉子", "knife": "刀", "spoon": "勺子", "bowl": "碗",
    "banana": "香蕉", "apple": "苹果", "sandwich": "三明治", "orange": "橙子",
    "broccoli": "西兰花", "carrot": "胡萝卜", "hot dog": "热狗", "pizza": "披萨",
    "donut": "甜甜圈", "cake": "蛋糕", "chair": "椅子", "couch": "沙发",
    "potted plant": "盆栽", "bed": "床", "dining table": "桌子", "toilet": "马桶",
    "tv": "屏幕", "laptop": "电脑", "mouse": "鼠标", "remote": "遥控器",
    "keyboard": "键盘", "cell phone": "手机", "microwave": "微波炉", "oven": "烤箱",
    "toaster": "烤面包机", "sink": "水槽", "refrigerator": "冰箱", "book": "书",
    "clock": "时钟", "vase": "花瓶", "scissors": "剪刀", "teddy bear": "玩偶",
    "hair drier": "吹风机", "toothbrush": "牙刷",
}


@dataclass
class Detection:
    class_id: int
    name: str
    score: float
    box: tuple[float, float, float, float]   # x, y, w, h in 640-letterbox space


@dataclass
class TagResult:
    tags: list[str] = field(default_factory=list)
    frames: int = 0
    detections: int = 0
    error: str | None = None


def decode_yolo(out: np.ndarray, conf: float = 0.25, iou: float = 0.45) -> list[Detection]:
    """Decode a (1, 84, 8400) YOLOv8 output into detections with NMS."""
    pred = out[0]
    boxes = pred[:4].T
    scores = pred[4:].T
    class_ids = scores.argmax(1)
    confs = scores.max(1)
    keep = confs > conf
    boxes, confs, class_ids = boxes[keep], confs[keep], class_ids[keep]
    if len(boxes) == 0:
        return []

    xywh = [[float(x - w / 2), float(y - h / 2), float(w), float(h)] for x, y, w, h in boxes]
    try:
        import cv2  # optional: NMS only
        idx = cv2.dnn.NMSBoxes(xywh, confs.tolist(), conf, iou)
        order = np.array(idx).flatten() if len(idx) else []
    except Exception:
        order = _nms_numpy(xywh, confs, iou)

    result = []
    for i in order:
        x, y, w, h = boxes[i]
        cid = int(class_ids[i])
        result.append(Detection(cid, COCO_NAMES[cid], float(confs[i]), (float(x), float(y), float(w), float(h))))
    return result


def _nms_numpy(boxes, scores, iou_threshold):
    """Fallback NMS when OpenCV is unavailable."""
    order = np.argsort(-scores)
    keep = []
    while order.size:
        i = int(order[0])
        keep.append(i)
        rest = order[1:]
        if not rest.size:
            break
        xx1 = np.maximum(boxes[i][0], np.array([boxes[j][0] for j in rest]))
        yy1 = np.maximum(boxes[i][1], np.array([boxes[j][1] for j in rest]))
        xx2 = np.minimum(boxes[i][0] + boxes[i][2], np.array([boxes[j][0] + boxes[j][2] for j in rest]))
        yy2 = np.minimum(boxes[i][1] + boxes[i][3], np.array([boxes[j][1] + boxes[j][3] for j in rest]))
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        area_i = boxes[i][2] * boxes[i][3]
        areas = np.array([boxes[j][2] * boxes[j][3] for j in rest])
        union = area_i + areas - inter
        iou = inter / np.maximum(union, 1e-9)
        order = rest[iou <= iou_threshold]
    return keep


class Detector:
    """Thin wrapper over an ONNX Runtime session. Thread-safe for `run` calls."""

    def __init__(self, model_path: str | Path, threads: int = 2, conf: float = 0.25, iou: float = 0.45):
        if np is None:
            raise RuntimeError("AI tagging needs numpy: pip install numpy onnxruntime")
        import onnxruntime as ort

        model_path = Path(model_path)
        if not model_path.is_file():
            raise FileNotFoundError(f"model not found: {model_path}")
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, threads)
        opts.inter_op_num_threads = 1
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(model_path), opts, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.conf = conf
        self.iou = iou
        self.model_id = f"{model_path.name}:{model_path.stat().st_size}"

    def detect(self, frame_rgb: np.ndarray) -> list[Detection]:
        blob = frame_rgb.transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        out = self.session.run(None, {self.input_name: blob})[0]
        return decode_yolo(out, self.conf, self.iou)


def frame_timestamps(duration: float, count: int) -> list[float]:
    """Evenly spaced timestamps, avoiding the very start/end (often black)."""
    if duration <= 0 or count <= 0:
        return []
    count = max(1, count)
    return [duration * (i + 1) / (count + 1) for i in range(count)]


def extract_frame(ffmpeg: str, path: str | Path, timestamp: float, timeout: float = 20.0) -> np.ndarray | None:
    """Grab one frame as 640x640 RGB through an ffmpeg pipe (no temp files)."""
    if np is None:
        return None
    vf = (
        f"scale={INPUT_SIZE}:{INPUT_SIZE}:force_original_aspect_ratio=decrease,"
        f"pad={INPUT_SIZE}:{INPUT_SIZE}:(ow-iw)/2:(oh-ih)/2:color=0x{PAD_COLOR:06x}"
    )
    cmd = [
        ffmpeg, "-v", "error", "-nostdin", "-ss", f"{timestamp:.3f}", "-i", str(path),
        "-frames:v", "1", "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    startupinfo = None
    if hasattr(subprocess, "STARTUPINFO"):   # Windows: no console flash per frame
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout, startupinfo=startupinfo)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if len(proc.stdout) != RAW_FRAME_BYTES:
        return None
    return np.frombuffer(proc.stdout, dtype=np.uint8).reshape(INPUT_SIZE, INPUT_SIZE, 3)


def aggregate_tags(votes: dict[str, int], frames: int) -> list[str]:
    """Keep classes seen in at least half the sampled frames, ordered by votes."""
    if not votes:
        return []
    threshold = max(1, math.ceil(frames / 2)) if frames else 1
    kept = [name for name, n in votes.items() if n >= threshold]
    if not kept:
        kept = [max(votes, key=lambda name: votes[name])]
    return sorted(kept, key=lambda n: (-votes[n], n))


def tag_media(
    detector: Detector,
    ffmpeg: str,
    path: str | Path,
    duration: float,
    sample_count: int = 3,
    cancel_event: threading.Event | None = None,
) -> TagResult:
    """Sample frames from a video and return stable Chinese tags."""
    frames = []
    for ts in frame_timestamps(duration, sample_count):
        if cancel_event is not None and cancel_event.is_set():
            break
        frame = extract_frame(ffmpeg, path, ts)
        if frame is not None:
            frames.append(frame)
    if not frames:
        return TagResult(error="no frames decoded")

    votes: dict[str, int] = {}
    total_det = 0
    for frame in frames:
        for det in detector.detect(frame):
            zh = ZH_TAGS.get(det.name, det.name)
            votes[zh] = votes.get(zh, 0) + 1
            total_det += 1
    return TagResult(tags=aggregate_tags(votes, len(frames)), frames=len(frames), detections=total_det)

def find_model(configured: str | None = None) -> Path | None:
    """Resolve the ONNX model: configured path, then <project>/models/*.onnx."""
    if configured:
        p = Path(configured).expanduser()
        if p.is_file():
            return p
    roots: list[Path] = []
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        # PyInstaller onefile/onedir: data files live beside the extracted
        # modules, not in the source tree.
        roots.append(Path(bundle) / "models")
    roots += [Path(__file__).resolve().parents[3] / "models", Path.cwd() / "models"]
    for root in roots:
        if not root.is_dir():
            continue
        files = sorted(root.glob("*.onnx"))
        if not files:
            continue
        preferred = [f for f in files if "fp32" in f.name.lower()] or files
        return preferred[0]
    return None
