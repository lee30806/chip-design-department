"""WaveJSON 처리는 pipeline/spec/wavejson.py로 옮겼다. X2 스크립트가 쓰던 이름을 그대로 내보낸다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from pipeline.spec.wavejson import compare, expand, flatten, norm_name, parse_wavejson, render  # noqa: E402,F401
