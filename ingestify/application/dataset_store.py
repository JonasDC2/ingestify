import hashlib
import mimetypes
from dataclasses import asdict
from io import BytesIO, StringIO
from typing import Dict, List, Optional

from ingestify.domain.models.event import EventBus
from ingestify.domain.models import (
    Dataset,
    DatasetCollection,
    DatasetRepository,
    DraftFile,
    File,
    LoadedFile,
    FileRepository,
    Identifier,
    Selector,
    Version,
    DatasetCreated,
)
from ingestify.utils import utcnow


class DatasetStore:
    def __init__(
        self,
        dataset_repository: DatasetRepository,
        file_repository: FileRepository,
    ):
        self.dataset_repository = dataset_repository
        self.file_repository = file_repository
        self.event_bus: Optional[EventBus] = None

    def set_event_bus(self, event_bus: EventBus):
        self.event_bus = event_bus

    def dispatch(self, event):
        if self.event_bus:
            self.event_bus.dispatch(event)

    def get_dataset_collection(
        self,
        dataset_type: Optional[str] = None,
        provider: Optional[str] = None,
        selector: Optional[Selector] = None,
        **kwargs
    ) -> DatasetCollection:
        return self.dataset_repository.get_dataset_collection(
            dataset_type=dataset_type, provider=provider, selector=selector, **kwargs
        )

    def _persist_files(
        self,
        dataset: Dataset,
        version_id: int,
        modified_files: Dict[str, Optional[DraftFile]],
    ) -> List[File]:
        modified_files_ = []

        current_version = dataset.current_version

        for filename, file_ in modified_files.items():
            if isinstance(file_, (str, bytes, BytesIO, StringIO)):
                if isinstance(file_, str):
                    stream = BytesIO(file_.encode("utf-8"))
                elif isinstance(file_, bytes):
                    stream = BytesIO(file_)
                elif isinstance(file_, StringIO):
                    stream = BytesIO(file_.read().encode("utf-8"))
                elif isinstance(file_, BytesIO):
                    stream = file_
                else:
                    raise Exception("not possible")

                data = stream.read()
                size = len(data)
                tag = hashlib.sha1(data).hexdigest()
                stream.seek(0)

                if (
                    current_version
                    and (
                        current_file := current_version.modified_files_map.get(filename)
                    )
                    and current_file.tag == tag
                ):
                    file_ = None
                else:
                    file_ = DraftFile(
                        modified_at=utcnow(),
                        content_type=mimetypes.guess_type(filename)[0],
                        tag=tag,
                        size=size,
                        stream=stream,
                    )

            if isinstance(file_, DraftFile):

                # TODO: check if this is a very clean way to go from DraftFile to File
                #
                # The format of the file_id is depending on the FileRepository type
                # For example S3FileRepository can use a full key as file_id,
                # while some database storage can use an uuid. It's up to the
                # repository to define the file_id
                file = File.from_draft(file_, filename)

                self.file_repository.save_content(
                    dataset,
                    version_id,
                    filename,
                    file_.stream
                )

                modified_files_.append(file)

        return modified_files_

    def add_version(
        self, dataset: Dataset, files: Dict[str, DraftFile], description: str = "Update"
    ):
        """
        Create new version first, so FileRepository can use
        version_id in the key.
        """
        version_id = dataset.next_version_id()
        created_at = utcnow()

        persisted_files_ = self._persist_files(dataset, version_id, files)
        dataset.add_version(
            Version(
                version_id=version_id,
                created_at=created_at,
                description=description,
                modified_files=persisted_files_,
            )
        )

        self.dataset_repository.save(dataset)

    def create_dataset(
        self,
        dataset_type: str,
        provider: str,
        dataset_identifier: Identifier,
        files: Dict[str, DraftFile],
        description: str = "Update",
    ):
        dataset = Dataset(
            dataset_id=self.dataset_repository.next_identity(),
            identifier=dataset_identifier,
            dataset_type=dataset_type,
            provider=provider,
            metadata=getattr(dataset_identifier, '_metadata', {})
        )
        self.add_version(dataset, files, description)

        self.dispatch(DatasetCreated(dataset=dataset))

    def load_files(self, dataset: Dataset) -> Dict[str, LoadedFile]:
        current_version = dataset.current_version
        files = {}
        for file in current_version.modified_files:
            loaded_file = LoadedFile(
                stream=self.file_repository.load_content(
                    dataset=dataset,
                    version_id=current_version.version_id,
                    filename=file.filename
                ),
                **asdict(file)
            )
            files[file.filename] = loaded_file
        return files

    def load_with_kloppy(self, dataset: Dataset, **kwargs):
        files = self.load_files(dataset)
        if dataset.provider == "statsbomb":
            from kloppy import statsbomb
            return statsbomb.load(
                event_data=files['events.json'].stream,
                lineup_data=files['lineups.json'].stream,
                **kwargs
            )
