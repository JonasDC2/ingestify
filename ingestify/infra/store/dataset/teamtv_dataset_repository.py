from typing import Optional


from ingestify.domain.models import (
    Dataset,
    DatasetCollection,
    DatasetRepository,
    Selector,
)
from ingestify.infra.store.dataset.http_dataset_repository import HTTPDatasetRepository


def parse_value(v):
    try:
        return int(v)
    except ValueError:
        return v


class TeamTVDatasetRepository(DatasetRepository):
    @classmethod
    def supports(cls, url: str) -> bool:
        return url.startswith("teamtv://")

    def __init__(self, url: str):
        self.bucket = url[9:]
        self.http_repository = HTTPDatasetRepository(
            #url=f"https://api.teamtvsport.com/api/ingestify/{bucket}"
            url="http://127.0.0.1:8080/api/buckets/{bucket}/datasets"
        )

    def get_dataset_collection(
        self,
        bucket: Optional[str] = None,
        dataset_type: Optional[str] = None,
        provider: Optional[str] = None,
        selector: Optional[Selector] = None,
        **kwargs
    ) -> DatasetCollection:
        return self.http_repository.get_dataset_collection(
            dataset_type=dataset_type,
            provider=provider,
            selector=selector,
            bucket=bucket or self.bucket,
            **kwargs
        )

    def save(self, dataset: Dataset):
        if not dataset.bucket:
            dataset.bucket = self.bucket
        return self.http_repository.save(dataset)

    def next_identity(self):
        return self.http_repository.next_identity()
