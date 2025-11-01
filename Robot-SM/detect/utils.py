from __future__ import annotations

from typing import Union

import cv2
import numpy as np


def open_source(source: str, is_image: bool) -> Union[int, str, np.ndarray]:
    """Chuẩn hóa nguồn vào:
    - Nếu là ảnh tĩnh: trả về ndarray
    - Nếu là camera index (string digit): trả về int
    - Nếu là đường dẫn video: trả về string path
    """
    if is_image:
        img = cv2.imread(source)
        if img is None:
            raise FileNotFoundError(f"Không đọc được ảnh: {source}")
        return img
    if source.isdigit():
        return int(source)
    return source


def should_quit(key: int) -> bool:
    return key in (27, ord("q"), ord("Q"))
