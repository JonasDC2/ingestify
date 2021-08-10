import os
import shutil
from pathlib import Path
from typing import IO, AnyStr

from domain.models import Dataset, FileRepository


class LocalFileRepository(FileRepository):
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)

    def save_content(self, file_key: str, stream: IO[AnyStr]):
        full_path = self.base_dir / file_key
        full_path.parent.mkdir(parents=True, exist_ok=True)

        with open(full_path, "wb") as fp:
            shutil.copyfileobj(stream, fp)

    def load_content(self, file_key: str) -> IO[AnyStr]:
        pass

    def get_key(self, dataset: Dataset, version_id: int, filename: str) -> str:
        return str(Path(dataset.dataset_id) / str(version_id) / filename)
