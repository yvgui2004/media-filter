# Local AI model / 本地 AI 模型

This repository does **not** include model weights. To use local or hybrid AI
tagging, place a YOLOv8 detection ONNX model here as `yolov8n_fp32.onnx`
(640x640 input), or choose another file in **Settings → AI model**.

The README has an export command. Scanning and cloud-only tagging work without
this file.

Ultralytics YOLOv8 weights are **AGPL-3.0**; comply with that license if you
redistribute them.

---

仓库**不附带**模型权重。本地 / 混合模式需要在当前目录放一个 YOLOv8 检测 ONNX，
命名为 `yolov8n_fp32.onnx`（640×640 输入），或在**设置 → AI 模型**里指定其他路径。

导出命令见 README。纯扫描和全云端识别不需要这个文件。

Ultralytics YOLOv8 权重为 **AGPL-3.0**，再分发时请遵守对应许可。