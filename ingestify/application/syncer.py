import logging
from datetime import timedelta
from typing import Dict, List, Tuple

from domain.models import (Dataset, Identifier, Selector, Source, Task,
                           TaskSet, dataset_repository_factory,
                           file_repository_factory, source_factory)
from utils import utcnow

from .store import Store

logger = logging.getLogger(__name__)


class FetchPolicy:
    def __init__(self):
        # refresh all data that changed less than two day ago
        self.min_age = utcnow() - timedelta(days=2)
        self.last_change = utcnow() - timedelta(days=1)

    def should_fetch(self, dataset_identifier: Identifier) -> bool:
        # this is called when dataset does not exist yet
        return True

    def should_refetch(self, dataset: Dataset) -> bool:
        current_version = dataset.current_version

        if not dataset.versions:
            return True
        # elif self.last_change > current_version.created_at > self.min_age:
        #    return True
        else:
            return False


class UpdateDatasetTask(Task):
    def __init__(self, source: Source, dataset: Dataset, store: Store):
        self.source = source
        self.dataset = dataset
        self.store = store

    def run(self):
        files = self.source.fetch_dataset_files(
            self.dataset.identifier, current_version=self.dataset.current_version
        )
        self.store.add_version(self.dataset, files)

    def __repr__(self):
        return f"UpdateDatasetTask({self.source} -> {self.dataset.identifier})"


class CreateDatasetTask(Task):
    def __init__(self, source: Source, dataset_identifier: Identifier, store: Store):
        self.source = source
        self.dataset_identifier = dataset_identifier
        self.store = store

    def run(self):
        files = self.source.fetch_dataset_files(
            self.dataset_identifier, current_version=None
        )
        self.store.create_dataset(
            dataset_type=self.source.dataset_type,
            provider=self.source.provider,
            dataset_identifier=self.dataset_identifier,
            files=files,
        )

    def __repr__(self):
        return f"CreateDatasetTask({self.source} -> {self.dataset_identifier})"


class Syncer:
    def __init__(self, dataset_url: str, file_url: str):
        file_repository = file_repository_factory.build_if_supports(
            url=file_url
        )
        # dataset_repository = SqlAlchemyDatasetRepository("sqlite:///:memory:")
        dataset_repository = dataset_repository_factory.build_if_supports(
            url=dataset_url
        )

        self.store = Store(
            dataset_repository=dataset_repository, file_repository=file_repository
        )

        self.fetch_policy = FetchPolicy()

        self.selectors: List[Tuple[str, Selector]] = []

    def add_selector(self, source_name: str, **selector: Dict):
        self.selectors.append((source_name, Selector(**selector)))

    def collect_and_run(self):
        task_set = TaskSet()

        for source_name, selector in self.selectors:
            source = source_factory.build(source_name)

            logger.info(
                f"Discovering datasets from {source_name} using selector {selector}"
            )
            dataset_identifiers = [
                Identifier.create_from(selector, **identifier)
                for identifier in source.discover_datasets(
                    **selector.filtered_attributes
                )
            ]
            logger.info(f"Found {len(dataset_identifiers)} datasets")

            task_subset = TaskSet()

            dataset_collection = self.store.get_dataset_collection(
                dataset_type=source.dataset_type,
                provider=source.provider,
                selector=selector,
            )

            skip_count = 0
            for dataset_identifier in dataset_identifiers:
                if dataset := dataset_collection.get(dataset_identifier):
                    if self.fetch_policy.should_refetch(dataset):
                        task_subset.add(
                            UpdateDatasetTask(
                                source=source, dataset=dataset, store=self.store
                            )
                        )
                    else:
                        skip_count += 1
                else:
                    if self.fetch_policy.should_fetch(dataset_identifier):
                        task_subset.add(
                            CreateDatasetTask(
                                source=source,
                                dataset_identifier=dataset_identifier,
                                store=self.store,
                            )
                        )
                    else:
                        skip_count += 1

            logger.info(f"Created {len(task_subset)} tasks")
            logger.info(f"Skipping {skip_count} datasets due to fetch policy")

            task_set += task_subset

        logger.info(f"Found {len(task_set)} tasks")

        for task in task_set:
            logger.info(f"Running task {task}")
            task.run()