import os
from typing import List
import supervisely as sly
from supervisely import batched
from supervisely.app.widgets import Progress
from supervisely.api.file_api import FileInfo

BATCH_SIZE = 50


def import_team_files(
    api: sly.Api,
    foreign_api: sly.Api,
    team_id: int,
    remote_paths: List[str],
    progress_upload: Progress,
    progress_download: Progress,
):
    team = foreign_api.team.get_info_by_id(team_id)
    res_team = api.team.get_info_by_name(team.name)
    if res_team is None:
        res_team = api.team.create(team.name, description=team.description)

    files_to_upload = []
    for remote_path in remote_paths:
        file: FileInfo = foreign_api.file.get_info_by_path(team_id, remote_path)
        if file is None:  # directory
            dir_files = foreign_api.file.list(team_id, remote_path, True, return_type="fileinfo")
            files_to_upload.extend(dir_files)
        else:
            files_to_upload.append(file)

    storage_dir = "storage"
    sly.fs.mkdir(storage_dir)
    local_paths = []
    remote_paths = []
    with progress_upload(
        message="Downloading Team Files", total=len(files_to_upload)
    ) as pbar_download_total:
        for batch_files in batched(files_to_upload):
            for file in batch_files:
                file: FileInfo
                with progress_download(
                    message=f"Downloading {file.name}",
                    total=file.sizeb,
                    unit="iB",
                    unit_scale=True,
                ) as pbar_download:
                    progress_download.show()
                    remote_path = file.path
                    local_path = os.path.join(storage_dir, remote_path.lstrip("/"))

                    if api.file.exists(res_team.id, file.path):
                        sly.logger.warn(f'File: "{file.path}" already exists')
                        pbar_download.update(file.sizeb)
                        pbar_download_total.update()
                        continue

                    foreign_api.file.download(
                        team_id=team_id,
                        remote_path=remote_path,
                        local_save_path=local_path,
                        progress_cb=pbar_download.update,
                    )
                    local_paths.append(local_path), remote_paths.append(remote_path)
                pbar_download_total.update()
            progress_download.hide()

    with progress_upload(message="Uploading Team Files", total=len(local_paths)) as pbar_upload:
        if len(local_paths) == 0:
            pbar_upload.update(len(local_paths))
            return
        for local_paths_batch, remote_paths_batch in zip(
            batched(local_paths, BATCH_SIZE), batched(remote_paths, BATCH_SIZE)
        ):
            api.file.upload_bulk(
                team_id=res_team.id, src_paths=local_paths_batch, dst_paths=remote_paths_batch
            )
            pbar_upload.update(len(local_paths_batch))
            for p in local_paths_batch:
                sly.fs.silent_remove(p)
