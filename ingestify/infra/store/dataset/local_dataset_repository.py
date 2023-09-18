import glob
import os
import pickle
import uuid
from pathlib import Path
from typing import Optional

from ingestify.domain.models import (
    Dataset,
    DatasetCollection,
    DatasetRepository,
    Selector,
)


def parse_value(v):
    try:
        return int(v)
    except ValueError:
        return v


class LocalDatasetRepository(DatasetRepository):
    def destroy_dataset(self, dataset_id: str):
        pass

    @classmethod
    def supports(cls, url: str) -> bool:
        return url.startswith("file://")

    def __init__(self, url: str):
        self.base_dir = Path(url[7:])

    def get_dataset_collection(
        self,
        dataset_type: Optional[str] = None,
        provider: Optional[str] = None,
        selector: Optional[Selector] = None,
        **kwargs
    ) -> DatasetCollection:

        datasets = []
        for dir_name in glob.glob(str(self.base_dir / "*")):
            attributes = {
                item[0]: parse_value(item[1])
                for item in [
                    part.split("=") for part in os.path.basename(dir_name).split("__")
                ]
            }
            if not selector or selector.matches(attributes):
                with open(dir_name + "/dataset.pickle", "rb") as fp:
                    dataset = pickle.load(fp)
                datasets.append(dataset)
        return DatasetCollection(datasets)

    def save(self, bucket: str, dataset: Dataset):
        full_path = (
            self.base_dir / dataset.identifier.key.replace("/", "__") / "dataset.pickle"
        )
        full_path.parent.mkdir(parents=True, exist_ok=True)

        with open(full_path, "wb") as fp:
            pickle.dump(dataset, fp)

    def next_identity(self):
        return str(uuid.uuid4())
