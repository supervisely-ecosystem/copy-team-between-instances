import anyio
import os
import time
from typing import List
import supervisely as sly
from urllib.parse import urlparse
from supervisely import batched, KeyIdMap, DatasetInfo
from supervisely.project.project_type import ProjectType
from supervisely.app.widgets import Progress
from supervisely.api.module_api import ApiField
from supervisely.api.image_api import ImageInfo
from supervisely.api.video.video_api import VideoInfo
from supervisely.api.volume.volume_api import VolumeInfo
from supervisely.api.pointcloud.pointcloud_api import PointcloudInfo
from supervisely.io.fs import mkdir, silent_remove

BATCH_SIZE = 50


def change_link(bucket_path: str, link: str):
    parsed_url = urlparse(link)
    return f"{bucket_path}{parsed_url.path}"


def retyr_if_end_stream(func):
    # decorator to retry 5 times function if it raises EndOfStream exception
    def wrapper(*args, **kwargs):
        for i in range(5):
            try:
                return func(*args, **kwargs)
            except (anyio.EndOfStream, FileNotFoundError) as e:
                if i == 4:
                    raise e
                sly.logger.warn(f"Error occurred while downloading/uploading images. Retrying... {i + 1}/5")
                time.sleep(2)
    
    return wrapper
            


@retyr_if_end_stream
def download_upload_images(
    foreign_api: sly.Api,
    api: sly.Api,
    dataset: DatasetInfo,
    res_dataset: DatasetInfo,
    images_ids: List[int],
    images_paths: List[str],
    images_names: List[str],
    images_metas: List[dict],
    images_hashs: List[str],
    existing_images: List[str],
):  
    for p in images_paths:
        silent_remove(p)

    res_images = []
    if all([name in existing_images for name in images_names]):
        sly.logger.info("Current batch of images already exist in destination dataset. Skipping...")
        return [existing_images[name] for name in images_names]
    elif any([name in existing_images for name in images_names]):
        sly.logger.info("Some images in batch already exist in destination dataset. Downloading only missing images.")
        for id, path, name, meta in zip(images_ids, images_paths, images_names, images_metas):
            if name in existing_images:
                img = existing_images[name]
                res_images.append(img)
            else:
                foreign_api.image.download_path(id, path)
                img = api.image.upload_path(
                    dataset_id=res_dataset.id,
                    name=name,
                    path=path,
                    meta=meta,
                )
                silent_remove(path)
                res_images.append(img)
    if all([hash is not None for hash in images_hashs]):
        try:
            sly.logger.info("Attempting to upload images by hash.")
            res_images = api.image.upload_hashes(
                dataset_id=res_dataset.id,
                names=images_names,
                hashes=images_hashs,
                metas=images_metas,
            )
            return res_images
        except Exception as e:
            sly.logger.info(f"Failed uploading images by hash. Attempting to upload images with paths. {e}")

    foreign_api.image.download_paths(
        dataset_id=dataset.id,
        ids=images_ids,
        paths=images_paths,
    )
    res_images = api.image.upload_paths(
        dataset_id=res_dataset.id,
        names=images_names,
        paths=images_paths,
        metas=images_metas,
    )
    for p in images_paths:
        silent_remove(p)
    return res_images


def process_images(
    api: sly.Api,
    foreign_api: sly.Api,
    dataset: sly.DatasetInfo,
    res_dataset: sly.DatasetInfo,
    meta: sly.ProjectMeta,
    progress_items: Progress,
    is_fast_mode: bool = False,
    need_change_link: bool = False,
    bucket_path: str = None,
):
    storage_dir = "storage"
    mkdir(storage_dir, True)
    images: List[ImageInfo] = foreign_api.image.get_list(dataset.id)
    existing_images = api.image.get_list(res_dataset.id)
    existing_images = {img.name: img for img in existing_images}
    
    with progress_items(
        message=f"Importing images from dataset: {dataset.name}", total=len(images)
    ) as pbar:
        for images_batch in batched(images, BATCH_SIZE):
            images_ids = [image.id for image in images_batch]
            images_names = [image.name for image in images_batch]
            images_metas = [image.meta for image in images_batch]
            images_paths = [os.path.join(storage_dir, image_name) for image_name in images_names]
            images_hashs = [image.hash for image in images_batch]

            images_links = []
            if is_fast_mode:
                for image in images:
                    if image.link is not None:
                        link = image.link
                        if need_change_link:
                            link = change_link(bucket_path, link)
                        images_links.append(link)

            if len(images_links) == len(images_batch):
                try:
                    res_images = api.image.upload_links(
                        dataset_id=res_dataset.id,
                        names=images_names,
                        links=images_links,
                        metas=images_metas,
                        force_metadata_for_links=False,
                        skip_validation=False,
                    )

                    success = True
                    for image in res_images:
                        if image.width is None or image.height is None:
                            success = False
                            break
                    if success is False:
                        api.image.remove_batch(ids=[image.id for image in res_images])
                        sly.logger.warn(
                            "Links are not accessible or invalid. Attempting to download images with paths"
                        )
                        raise Exception(
                            "Links are not accessible or invalid. Attempting to download images with paths"
                        )

                except Exception:
                    res_images = download_upload_images(
                        foreign_api,
                        api,
                        dataset,
                        res_dataset,
                        images_ids,
                        images_paths,
                        images_names,
                        images_metas,
                        images_hashs,
                        existing_images,
                    )
            else:
                res_images = download_upload_images(
                    foreign_api,
                    api,
                    dataset,
                    res_dataset,
                    images_ids,
                    images_paths,
                    images_names,
                    images_metas,
                    images_hashs,
                    existing_images,
                )

            res_images_ids = [image.id for image in res_images]
            annotations = foreign_api.annotation.download_json_batch(
                dataset_id=dataset.id,
                image_ids=images_ids,
                force_metadata_for_links=False,
            )
            api.annotation.upload_jsons(img_ids=res_images_ids, ann_jsons=annotations)
            pbar.update(len(images_batch))


def process_videos(
    api: sly.Api,
    foreign_api: sly.Api,
    dataset: DatasetInfo,
    res_dataset: DatasetInfo,
    meta: sly.ProjectMeta,
    progress_items: Progress,
    is_fast_mode: bool = False,
    need_change_link: bool = False,
    bucket_path: str = None,
):
    storage_dir = "storage"
    mkdir(storage_dir, True)
    key_id_map = KeyIdMap()
    videos: List[VideoInfo] = foreign_api.video.get_list(dataset_id=dataset.id, raw_video_meta=True)
    with progress_items(
        message=f"Importing videos from dataset: {dataset.name}", total=len(videos)
    ) as pbar:
        for video in videos:
            try:
                if video.link is not None and is_fast_mode:
                    link = video.link
                    if need_change_link:
                        link = change_link(bucket_path, link)
                    res_video = api.video.upload_link(
                        dataset_id=res_dataset.id, link=link, name=video.name, skip_download=True
                    )
                elif video.hash is not None:
                    res_video = api.video.upload_hash(
                        dataset_id=res_dataset.id, name=video.name, hash=video.hash
                    )
            except Exception:
                video_path = os.path.join(storage_dir, video.name)
                foreign_api.video.download_path(id=video.id, path=video_path)
                res_video = api.video.upload_path(
                    dataset_id=res_dataset.id,
                    name=video.name,
                    path=video_path,
                    meta=video.meta,
                )
                silent_remove(video_path)

            ann_json = foreign_api.video.annotation.download(video_id=video.id)
            ann = sly.VideoAnnotation.from_json(
                data=ann_json, project_meta=meta, key_id_map=key_id_map
            )
            api.video.annotation.append(video_id=res_video.id, ann=ann, key_id_map=key_id_map)
            pbar.update()


def process_volumes(
    api: sly.Api,
    foreign_api: sly.Api,
    dataset: DatasetInfo,
    res_dataset: DatasetInfo,
    meta: sly.ProjectMeta,
    progress_items: Progress,
    is_fast_mode: bool = False,
    need_change_link: bool = False,
    bucket_path: str = None,
):
    storage_dir = "storage"
    mkdir(storage_dir, True)
    key_id_map = KeyIdMap()
    geometries_dir = f"geometries_{dataset.id}"
    sly.fs.mkdir(geometries_dir, True)
    volumes: List[VolumeInfo] = foreign_api.volume.get_list(dataset_id=dataset.id)
    with progress_items(
        message=f"Importing volumes from dataset: {dataset.name}", total=len(volumes)
    ) as pbar:
        # sly.download_volume_project
        for volume in volumes:
            if volume.hash:
                res_volume = api.volume.upload_hash(
                    dataset_id=res_dataset.id,
                    name=volume.name,
                    hash=volume.hash,
                    meta=volume.meta,
                )
            else:
                volume_path = os.path.join(storage_dir, volume.name)
                foreign_api.volume.download_path(id=volume.id, path=volume_path)
                res_volume = api.volume.upload_nrrd_serie_path(
                    dataset_id=res_dataset.id, name=volume.name, path=volume_path
                )
                silent_remove(volume_path)

            ann_json = foreign_api.volume.annotation.download(volume_id=volume.id)
            ann = sly.VolumeAnnotation.from_json(
                data=ann_json, project_meta=meta, key_id_map=key_id_map
            )
            api.volume.annotation.append(volume_id=res_volume.id, ann=ann, key_id_map=key_id_map)
            if ann.spatial_figures:
                geometries = []
                for sf in ann_json.get("spatialFigures"):
                    sf_id = sf.get("id")
                    path = os.path.join(geometries_dir, f"{sf_id}.nrrd")
                    foreign_api.volume.figure.download_stl_meshes([sf_id], [path])
                    with open(path, "rb") as file:
                        geometry_bytes = file.read()
                    geometries.append(geometry_bytes)
                api.volume.figure.upload_sf_geometry(
                    ann.spatial_figures, geometries, key_id_map=key_id_map
                )
                del geometries
            pbar.update()
        sly.fs.remove_dir(geometries_dir)


def process_pcd(
    api: sly.Api,
    foreign_api: sly.Api,
    dataset: DatasetInfo,
    res_dataset: DatasetInfo,
    meta: sly.ProjectMeta,
    progress_items: Progress,
    is_fast_mode: bool = False,
    need_change_link: bool = False,
    bucket_path: str = None,
):
    storage_dir = "storage"
    mkdir(storage_dir, True)
    key_id_map_initial = KeyIdMap()
    key_id_map_new = KeyIdMap()
    pcds: List[PointcloudInfo] = foreign_api.pointcloud.get_list(dataset_id=dataset.id)
    with progress_items(
        message=f"Importing point clouds from dataset: {dataset.name}", total=len(pcds)
    ) as pbar:
        for pcd in pcds:
            if pcd.hash:
                res_pcd = api.pointcloud.upload_hash(
                    dataset_id=res_dataset.id,
                    name=pcd.name,
                    hash=pcd.hash,
                    meta=pcd.meta,
                )
            else:
                pcd_path = os.path.join(storage_dir, pcd.name)
                foreign_api.pointcloud.download_path(id=pcd.id, path=pcd_path)
                res_pcd = api.pointcloud.upload_path(
                    dataset_id=res_dataset.id, name=pcd.name, path=pcd_path, meta=pcd.meta
                )
                silent_remove(pcd_path)

            ann_json = foreign_api.pointcloud.annotation.download(pointcloud_id=pcd.id)
            ann = sly.PointcloudAnnotation.from_json(
                data=ann_json, project_meta=meta, key_id_map=key_id_map_initial
            )
            api.pointcloud.annotation.append(
                pointcloud_id=res_pcd.id, ann=ann, key_id_map=key_id_map_new
            )
            rel_images = foreign_api.pointcloud.get_list_related_images(id=pcd.id)
            if len(rel_images) != 0:
                rimg_infos = []
                for rel_img in rel_images:
                    rimg_infos.append(
                        {
                            ApiField.ENTITY_ID: res_pcd.id,
                            ApiField.NAME: rel_img[ApiField.NAME],
                            ApiField.HASH: rel_img[ApiField.HASH],
                            ApiField.META: rel_img[ApiField.META],
                        }
                    )
                api.pointcloud.add_related_images(rimg_infos)

            pbar.update()


def process_pcde(
    api: sly.Api,
    foreign_api: sly.Api,
    dataset: DatasetInfo,
    res_dataset: DatasetInfo,
    meta: sly.ProjectMeta,
    progress_items: Progress,
    is_fast_mode: bool = False,
    need_change_link: bool = False,
    bucket_path: str = None,
):
    storage_dir = "storage"
    mkdir(storage_dir, True)
    key_id_map = KeyIdMap()
    pcdes = foreign_api.pointcloud_episode.get_list(dataset_id=dataset.id)
    ann_json = foreign_api.pointcloud_episode.annotation.download(dataset_id=dataset.id)
    ann = sly.PointcloudEpisodeAnnotation.from_json(
        data=ann_json, project_meta=meta, key_id_map=KeyIdMap()
    )
    frame_to_pointcloud_ids = {}
    with progress_items(
        message=f"Importing point cloud episodes from dataset: {dataset.name}", total=len(pcdes)
    ) as pbar:
        for pcde in pcdes:
            if pcde.hash:
                res_pcde = api.pointcloud_episode.upload_hash(
                    dataset_id=res_dataset.id,
                    name=pcde.name,
                    hash=pcde.hash,
                    meta=pcde.meta,
                )
            else:
                pcde_path = os.path.join(storage_dir, pcde.name)
                foreign_api.pointcloud_episode.download_path(id=pcde.id, path=pcde_path)
                res_pcde = api.pointcloud_episode.upload_path(
                    dataset_id=res_dataset.id, name=pcde.name, path=pcde_path, meta=pcde.meta
                )
                silent_remove(pcde_path)

            frame_to_pointcloud_ids[res_pcde.meta["frame"]] = res_pcde.id
            rel_images = foreign_api.pointcloud_episode.get_list_related_images(id=pcde.id)
            if len(rel_images) != 0:
                rimg_infos = []
                for rel_img in rel_images:
                    rimg_infos.append(
                        {
                            ApiField.ENTITY_ID: res_pcde.id,
                            ApiField.NAME: rel_img[ApiField.NAME],
                            ApiField.HASH: rel_img[ApiField.HASH],
                            ApiField.META: rel_img[ApiField.META],
                        }
                    )
                api.pointcloud_episode.add_related_images(rimg_infos)
            pbar.update()

        api.pointcloud_episode.annotation.append(
            dataset_id=res_dataset.id,
            ann=ann,
            frame_to_pointcloud_ids=frame_to_pointcloud_ids,
            key_id_map=key_id_map,
        )


def get_ws_projects_map(ws_collapse):
    ws_projects_map = {}
    for ws in ws_collapse._items:
        ws_projects_map[ws.name] = []
        projects = ws.content
        for project in projects.get_transferred_items():
            ws_projects_map[ws.name].append(project)
    return ws_projects_map


process_type_map = {
    ProjectType.IMAGES.value: process_images,
    ProjectType.VIDEOS.value: process_videos,
    ProjectType.VOLUMES.value: process_volumes,
    ProjectType.POINT_CLOUDS.value: process_pcd,
    ProjectType.POINT_CLOUD_EPISODES.value: process_pcde,
}


def import_workspaces(
    api: sly.Api,
    foreign_api: sly.Api,
    team_id: int,
    ws_collapse: sly.app.widgets.Collapse,
    progress_ws: Progress,
    progress_pr: Progress,
    progress_ds: Progress,
    progress_items: Progress,
    is_import_all_ws: bool = False,
    ws_collision_value: str = "check",
    is_fast_mode: bool = False,
    change_link_flag: bool = False,
    bucket_path: str = None,
):
    team = foreign_api.team.get_info_by_id(team_id)

    if is_import_all_ws:
        workspaces = foreign_api.workspace.get_list(team_id=team_id)
    else:
        ws_projects_map = get_ws_projects_map(ws_collapse)
        for ws in ws_collapse._items:
            ws_projects_map[ws.name] = []
            projects = ws.content
            for project in projects.get_transferred_items():
                ws_projects_map[ws.name].append(project)
        workspaces = [
            foreign_api.workspace.get_info_by_id(workspace_id)
            for workspace_id in ws_projects_map
            if len(ws_projects_map[workspace_id]) > 0
        ]

    res_team = api.team.get_info_by_name(team.name)
    if res_team is None:
        res_team = api.team.create(team.name, description=team.description)

    with progress_ws(
        message=f"Importing workspaces from team: {team.name}", total=len(workspaces)
    ) as pbar_ws:
        for workspace in workspaces:
            res_workspace = api.workspace.get_info_by_name(res_team.id, workspace.name)
            if res_workspace is None:
                res_workspace = api.workspace.create(
                    res_team.id, workspace.name, description=workspace.description
                )

            if is_import_all_ws:
                projects = foreign_api.project.get_list(workspace.id)
            else:
                projects = [
                    foreign_api.project.get_info_by_id(project_id)
                    for project_id in ws_projects_map[workspace.id]
                ]
            with progress_pr(
                message=f"Importing projects from workspace: {workspace.name}", total=len(projects)
            ) as pbar_pr:
                for project in projects:
                    temp_ws_collision = ws_collision_value
                    res_project = api.project.get_info_by_name(res_workspace.id, project.name)
                    if res_project is not None and res_project.type != str(sly.ProjectType.IMAGES) and temp_ws_collision == "check":
                        temp_ws_collision = "ignore"
                        sly.logger.info("Changing collision value to 'ignore' for non-image projects.")
                    if res_project is None:
                        res_project = api.project.create(
                            res_workspace.id,
                            project.name,
                            description=project.description,
                            type=project.type,
                        )
                    elif res_project is not None and temp_ws_collision == "reupload":
                        api.project.remove(res_project.id)
                        res_project = api.project.create(
                            res_workspace.id,
                            project.name,
                            description=project.description,
                            type=project.type,
                        )
                    
                    elif res_project is not None and temp_ws_collision == "ignore":
                        sly.logger.info(f"Project {project.name} already exists in destination workspace. Skipping...")
                        pbar_pr.update()
                        continue
                
                    elif res_project is not None and temp_ws_collision == "check":
                        sly.logger.info(f"Project {project.name} already exists in destination workspace. Checking...")

                    meta_json = foreign_api.project.get_meta(project.id)
                    api.project.update_meta(res_project.id, meta_json)
                    meta = sly.ProjectMeta.from_json(meta_json)

                    datasets = foreign_api.dataset.get_list(project.id)
                    with progress_ds(
                        message=f"Importing datasets from project: {project.name}",
                        total=len(datasets),
                    ) as pbar_ds:
                        for dataset in datasets:
                            res_dataset = api.dataset.get_info_by_name(res_project.id, dataset.name)
                            if res_dataset is None:
                                res_dataset = api.dataset.create(
                                    res_project.id, dataset.name, description=dataset.description
                                )
                            process_func = process_type_map.get(project.type)
                            process_func(
                                api=api,
                                foreign_api=foreign_api,
                                dataset=dataset,
                                res_dataset=res_dataset,
                                meta=meta,
                                progress_items=progress_items,
                                is_fast_mode=is_fast_mode,
                                need_change_link=change_link_flag,
                                bucket_path=bucket_path,
                            )
                            pbar_ds.update()
                    pbar_pr.update()
            pbar_ws.update()

    # progress_ws.hide()
    # progress_pr.hide()
    # progress_ds.hide()
    # progress_items.hide()
