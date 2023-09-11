from typing import List
from collections import defaultdict
import supervisely as sly
from supervisely import ProjectMeta
from supervisely.app.widgets import Progress
from supervisely.api.labeling_job_api import LabelingJobInfo
from supervisely.api.user_api import UserInfo
from supervisely.api.team_api import TeamInfo
from supervisely.api.project_api import ProjectInfo
from supervisely.api.dataset_api import DatasetInfo
from src.ui.entities.workspaces import process_type_map


def import_labeling_jobs(
    api: sly.Api,
    foreign_api: sly.Api,
    team_id: int,
    default_password: str,
    progress_job: Progress,
    progress_items: Progress,
):
    team = foreign_api.team.get_info_by_id(team_id)
    res_team = api.team.get_info_by_name(team.name)
    if res_team is None:
        res_team = api.team.create(team.name, description=team.description)

    existing_jobs: List[LabelingJobInfo] = api.labeling_job.get_list(team_id=res_team.id)
    existing_jobs_names = [job.name for job in existing_jobs]

    incoming_jobs: List[LabelingJobInfo] = foreign_api.labeling_job.get_list(team_id=team.id)
    with progress_job(message="Importing labeling jobs", total=len(incoming_jobs)) as pbar:
        for incoming_job in incoming_jobs:
            if incoming_job.name in existing_jobs_names:
                sly.logger.info(f"Labeling job {incoming_job.name} already exists.")
                pbar.update()
                continue

            job: LabelingJobInfo = api.labeling_job.get_info_by_name(res_team.id, incoming_job.name)
            if job is None:
                incoming_job: LabelingJobInfo = foreign_api.labeling_job.get_info_by_id(
                    incoming_job.id
                )
                job = create_job(
                    api, foreign_api, res_team, incoming_job, default_password, progress_items
                )
                pbar.update()


def create_job(
    api: sly.Api,
    foreign_api: sly.Api,
    res_team: TeamInfo,
    job: LabelingJobInfo,
    default_password: str,
    progress: Progress,
):
    # get job members
    creator, annotator, reviewer = get_or_create_members(
        api, foreign_api, res_team, job, default_password
    )
    workspace, project, dataset, meta = get_or_create_dataset(
        api, foreign_api, res_team, job, progress
    )

    job_meta, classes, tags, entities_ids = update_job_meta_classes(
        api, foreign_api, job, dataset, meta
    )

    # type problems
    images_range = job.images_range
    if images_range == (None, None):
        images_range = None

    res_jobs = api.labeling_job.create(
        name=job.name,
        dataset_id=dataset.id,
        user_ids=[annotator.id],
        readme=job.readme,
        description=job.description,
        classes_to_label=classes,
        objects_limit_per_image=job.objects_limit_per_image,
        tags_to_label=tags,
        tags_limit_per_image=job.tags_limit_per_image,
        include_images_with_tags=job.include_images_with_tags,
        exclude_images_with_tags=job.exclude_images_with_tags,
        images_range=images_range,
        reviewer_id=reviewer.id,
        images_ids=entities_ids,
        meta=job_meta,
    )
    for res_job in res_jobs:
        transfer_job_progress(api, foreign_api, job, res_job, meta)
        sly.logger.info(f'Labeling job "{res_job.name}" has been created.')


def get_or_create_members(
    api: sly.Api, foreign_api: sly.Api, team: TeamInfo, job: LabelingJobInfo, default_password: str
):
    # get job members
    creator_id, annotator_id, reviewer_id = job.created_by_id, job.assigned_to_id, job.reviewer_id
    creator, annotator, reviewer = None, None, None
    # get members of labeling job
    members_to_add: List[UserInfo] = []
    incoming_team_members: List[UserInfo] = foreign_api.user.get_team_members(job.team_id)
    for member in incoming_team_members:
        if member.id in [creator_id, annotator_id, reviewer_id]:
            if member.id == creator_id:
                creator = member
            if member.id == annotator_id:
                annotator = member
            if member.id == reviewer_id:
                reviewer = member
            members_to_add.append(member)

    existing_team_members: List[UserInfo] = api.user.get_team_members(team.id)
    existing_team_members_names = [member.login for member in existing_team_members]
    existing_members_map = {
        member.login: {"id": member.id, "role": member.role} for member in existing_team_members
    }
    roles_map = {role.role: role.id for role in api.role.get_list()}

    res_members: List[UserInfo] = []
    for member in members_to_add:
        if member.login not in existing_team_members_names:
            user = api.user.get_info_by_login(member.login)
            if user is None:
                user = api.user.create(
                    login=member.login,
                    password=default_password,
                    is_restricted=False,
                    name=member.name or "",
                    email=member.email or "",
                )
            try:
                api.user.add_to_team_by_login(member.login, team.id, roles_map[member.role])
            except:
                api.user.add_to_team_by_login(member.login, team.id, roles_map["annotator"])
        else:
            user = api.user.get_info_by_login(member.login)
            if user.login == "admin":
                res_members.append(user)
                continue
            if existing_members_map[member.login]["role"] != member.role:
                api.user.change_team_role(
                    existing_members_map[member.login]["id"], team.id, roles_map[member.role]
                )
        res_members.append(user)

    for member in res_members:
        if member.login == creator.login:
            creator = member
        if member.login == annotator.login:
            annotator = member
        if member.role == reviewer.login:
            reviewer = member

    return creator, annotator, reviewer


def get_or_create_dataset(
    api: sly.Api, foreign_api: sly.Api, team: TeamInfo, job: LabelingJobInfo, progress: Progress
):
    foreign_workspace_id = job.workspace_id
    foreign_project_id = job.project_id
    foreign_dataset_id = job.dataset_id

    # get or create workspace
    workspace = foreign_api.workspace.get_info_by_id(foreign_workspace_id)
    res_workspace = api.workspace.get_info_by_name(team.id, workspace.name)
    if res_workspace is None:
        res_workspace = api.workspace.create(
            team.id, workspace.name, description=workspace.description
        )

    # get or create project
    project = foreign_api.project.get_info_by_id(foreign_project_id)
    meta_json = foreign_api.project.get_meta(project.id)
    res_project = api.project.get_info_by_name(res_workspace.id, project.name)
    if res_project is None:
        res_project = api.project.create(
            res_workspace.id, project.name, type=project.type, description=project.description
        )

    # update project meta
    api.project.update_meta(res_project.id, meta_json)
    meta_json = api.project.get_meta(res_project.id)
    meta = sly.ProjectMeta.from_json(meta_json)

    # get or create dataset
    dataset = foreign_api.dataset.get_info_by_id(foreign_dataset_id)
    res_dataset = api.dataset.get_info_by_name(res_project.id, dataset.name)
    if res_dataset is None:
        res_dataset = api.dataset.create(
            res_project.id, dataset.name, description=dataset.description
        )
    else:
        sly.logger.info(f'Dataset: "{dataset.name}" already exists')
        return res_workspace, res_project, res_dataset, meta

    process_function = process_type_map[project.type]
    process_function(
        api=api,
        foreign_api=foreign_api,
        dataset=dataset,
        res_dataset=res_dataset,
        meta=meta,
        progress_items=progress,
    )

    return res_workspace, res_project, res_dataset, meta


def transfer_job_progress(
    api: sly.Api,
    foreign_api: sly.Api,
    job: LabelingJobInfo,
    res_job: LabelingJobInfo,
    meta: ProjectMeta,
):
    api.labeling_job.set_status(res_job.id, job.status)
    job_stats = foreign_api.labeling_job.get_stats(job.id)
    res_job_stats = api.labeling_job.get_stats(res_job.id)

    api.labeling_job.remove_all_figures(res_job.id)
    add_update_figures(api, foreign_api, res_job, job, job_stats, meta)
    # add_update_tags(api, foreign_api, res_job, job, job_stats, meta)
    update_entities(api, res_job.id, res_job_stats, job_stats)


def update_job_meta_classes(
    api: sly.Api,
    foreign_api: sly.Api,
    job: LabelingJobInfo,
    dataset: DatasetInfo,
    meta: ProjectMeta,
):
    job_meta = foreign_api.labeling_job.get_meta(job.id)
    job_classes = job_meta.get("classes")
    if job_classes is None:
        res_classes = []
    else:
        res_classes = []
        for job_class in job_classes:
            obj_class = meta.get_obj_class(job_class.get("name"))
            if obj_class is None:
                raise RuntimeError(
                    f"Class {job_class.get('name')} not found in Labeling Job: {job.name}"
                )
            res_classes.append(obj_class.name)

    job_tags = job_meta.get("projectTags")
    if job_tags is None:
        res_tags = []
    else:
        res_tags = []
        for job_tag in job_tags:
            tag = meta.get_tag_meta(job_tag.get("name"))
            if tag is None:
                raise RuntimeError(
                    f"Tag {job_tag.get('name')} not found in Labeling Job: {job.name}"
                )
            res_tags.append(tag.name)

    job_meta["classes"] = res_classes
    job_meta["projectTags"] = res_tags

    if job_meta["imageTags"] is None:
        filter_images_by_tags = []
        if job.include_images_with_tags is not None:
            for tag_name in job.include_images_with_tags:
                filter_images_by_tags.append({"name": tag_name, "positive": True})

        if job.exclude_images_with_tags is not None:
            for tag_name in job.exclude_images_with_tags:
                filter_images_by_tags.append({"name": tag_name, "positive": False})

        job_meta["imageTags"] = filter_images_by_tags

    if job.objects_limit_per_image is None:
        job_meta["imageFiguresLimit"] = 0

    if job.tags_limit_per_image is None:
        job_meta["imageTagsLimit"] = 0

    # update entitiesIds
    if job_meta.get("entityIds") is not None:
        # images
        res_ds_entities = api.image.get_list(dataset.id)

        f_entity_id_map = {entity["id"]: entity["name"] for entity in job.entities}
        entity_id_map = {entity.name: entity.id for entity in res_ds_entities}
        entities_ids = job_meta["entityIds"]
        res_entities = []
        for entity_id in entities_ids:
            image_name = f_entity_id_map[entity_id]
            image_id = entity_id_map[image_name]
            res_entities.append(image_id)
        job_meta["entityIds"] = res_entities

    return job_meta, res_classes, res_tags, res_entities


def add_update_figures(
    api: sly.Api,
    foreign_api: sly.Api,
    res_job: LabelingJobInfo,
    job: LabelingJobInfo,
    job_stats: dict,
    meta: ProjectMeta,
):
    foreign_job_classes = job_stats["classes"]
    foreign_job_classes_map = {obj["id"]: obj["name"] for obj in foreign_job_classes}
    entity_map = {entity["id"]: entity["name"] for entity in job.entities}
    figures_map = defaultdict(list)

    job_figures = foreign_api.labeling_job.get_figures(job.id)
    for figure in job_figures:
        figures_map[figure["entityId"]].append(figure)

    new_figures = []
    for entity_id in figures_map:
        res_entity = api.image.get_info_by_name(res_job.dataset_id, entity_map[entity_id])
        for figure in figures_map[entity_id]:
            res_object = meta.get_obj_class(foreign_job_classes_map[figure["classId"]])
            figure["classId"] = res_object.sly_id
            figure["entityId"] = res_entity.id
            new_figures.append(figure)

    res_figures = api.labeling_job.add_figures(res_job.id, new_figures)
    for figure in res_figures:
        api.labeling_job.update_figure_ann_duration(res_job.id, figure["id"], 3)


def add_update_tags(
    api: sly.Api,
    foreign_api: sly.Api,
    res_job: LabelingJobInfo,
    job: LabelingJobInfo,
    job_stats: dict,
    meta: ProjectMeta,
):
    pass


def update_entities(api: sly.Api, res_job_id: int, res_job_stats: dict, job_stats: dict):
    f_entity_duration_map = defaultdict(dict)
    for image in job_stats["images"]["images"]:
        f_entity_duration_map[image["name"]] = {
            "duration": image["annotationDuration"],
            "status": image["reviewStatus"],
        }

    entity_duration_map = defaultdict(dict)
    for image in res_job_stats["images"]["images"]:
        entity_name = image["name"]
        entity_id = image["id"]
        duration = f_entity_duration_map[image["name"]]["duration"]
        status = f_entity_duration_map[image["name"]]["status"]
        entity_duration_map[entity_name] = {"id": entity_id, "duration": duration, "status": status}

    for image in entity_duration_map:
        entity_id = entity_duration_map[image]["id"]
        duration = entity_duration_map[image]["duration"]
        status = entity_duration_map[image]["status"]
        # if duration != 0:
        #     api.labeling_job.update_entity_ann_duration(res_job_id, entity_id, duration)
        api.labeling_job.set_entity_status(res_job_id, entity_id, status)
