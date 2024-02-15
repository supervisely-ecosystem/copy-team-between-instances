import contextlib
import supervisely as sly
from typing import List
from supervisely.api.file_api import FileInfo
from supervisely.app.widgets import (
    Button,
    Checkbox,
    RadioGroup,
    Field,
    Card,
    Container,
    Text,
    Progress,
    Input,
    Table,
    Collapse,
    Transfer,
    ReloadableArea,
    FileViewer,
    Flexbox,
    Select,
    OneOf,
    Empty,
)

import src.globals as g
import src.ui.team_selector as team_selector
from src.ui.entities.workspaces import import_workspaces
from src.ui.entities.team_members import import_team_members
from src.ui.entities.labeling_jobs import import_labeling_jobs
from src.ui.entities.team_files import import_team_files


output_message = Text()
output_message.hide()


# Inputs
members_collision_items = [
    RadioGroup.Item(value="ignore", label="Leave members roles that already exists as they are"),
    RadioGroup.Item(value="reupload", label="Change members roles to match original team"),
]
members_collision = RadioGroup(members_collision_items, direction="vertical")
members_collision_field = Field(
    content=members_collision,
    title="Members collision",
    description="Select how to handle members that already exists",
)
team_members_d_password = Input(value="", placeholder="Enter default password for all users")
members_field_password = Field(
    content=team_members_d_password,
    title="Default Password",
    description="This password will be assigned to all created users. Don't forget to notify them about it.",
)
members_container = Container(widgets=[members_field_password, members_collision_field])

start_import = Button("Start Import")
start_import.hide()

import_progress_1 = Progress(hide_on_finish=False)
import_progress_2 = Progress(hide_on_finish=False)
import_progress_3 = Progress(hide_on_finish=True)
import_progress_4 = Progress(hide_on_finish=True)


# Entities collapses
ws_collision_items = [
    RadioGroup.Item(value="ignore", label="Skip projects that already exists"),
    RadioGroup.Item(value="check", label="Check if items in projects are the same and skip if so (works only for images projects)"),
    RadioGroup.Item(value="reupload", label="Remove and reupload projects that already exists"),
]
ws_collision = RadioGroup(ws_collision_items, direction="vertical")
ws_field_collision = Field(
    content=ws_collision,
    title="Data collision",
    description="Select how to handle projects that already exists",
)


bucket_text_info = Text()
connect_to_bucket = Button(text="Connect to bucket", icon="zmdi zmdi-cloud")
connect_bucket_flexbox = Flexbox(widgets=[connect_to_bucket, bucket_text_info])
bucket_name_input = Input(value="", placeholder="bucket name")
# providers = g.foreign_api.remote_storage.get_list_available_providers()
providers = [
    Select.Item(value="google", label="google cloud storage"),
    Select.Item(value="s3", label="amazon s3"),
    Select.Item(value="azure", label="azure storage"),
]
provider_selector = Select(providers)
provider_flexbox = Flexbox(widgets=[provider_selector, bucket_name_input])
need_link_change = Checkbox("Change transfer links for items")

change_link_tip_text = Text(
    "Cloud storage is required, structure in both storages must be the same.", status="info"
)
change_link_tip_text_2 = Text(
    (
        "For example, if you have images in your project linked to 'gcs://my-bucket/images/' "
        "and want to change them to 's3://other-bucket/images/' "
        "select 's3' in provider selector and input name of the new bucket only, "
        "assuming images directory is already manually created and populated in the new bucket"
    ),
    status="text",
    color="#808080",
)
bucket_options = Container(
    widgets=[
        change_link_tip_text,
        change_link_tip_text_2,
        provider_flexbox,
        connect_to_bucket,
        bucket_text_info,
    ]
)
bucket_options.hide()
options_container = Container(widgets=[need_link_change, bucket_options])
option_items = [
    RadioGroup.Item(
        value="slow",
        label="Copy data from instance to instance by reuploading (Slow)",
        content=Empty(),
    ),
    RadioGroup.Item(
        value="fast", label="Copy data by links, if possible (Fast)", content=options_container
    ),
]
ws_options = RadioGroup(option_items, direction="vertical")
ws_one_of = OneOf(ws_options)
ws_options_container = Container(widgets=[ws_options, ws_one_of])
ws_field_transfer = Field(
    content=ws_options_container,
    title="Data transfer",
    description="Select options how you would like to transfer data",
)

ws_collapse = Collapse()
ws_import_checkbox = Checkbox("Import all workspaces", checked=False)
ws_container = Container(
    widgets=[ws_import_checkbox, ws_collapse, ws_field_collision, ws_field_transfer]
)
ws_collapse.hide()

members_collapse = Transfer(titles=["Original Team", "Current Team"])
members_collapse.hide()
members_flexbox = Flexbox(
    widgets=[members_collapse, members_container],
)

tf_selector = FileViewer(files_list=[{"path": "/"}])
files_collapse_r = ReloadableArea()
files_collapse = Container(widgets=[])
files_collapse_r.set_content(files_collapse)
files_collapse.hide()

# Main collapse
entities_collapse_items = [
    Collapse.Item(name="Workspaces", title="Workspaces", content=ws_container),
    Collapse.Item(name="Team Members", title="Team Members", content=members_flexbox),
    Collapse.Item(name="Team Files", title="Team Files", content=files_collapse),
]
entities_collapse = Collapse(entities_collapse_items)
entities_collapse.hide()

reloadable_area = ReloadableArea()
reloadable_container = Container(widgets=[])
reloadable_area.set_content(reloadable_container)

import_settings = Container(
    widgets=[
        reloadable_area,
        output_message,
        start_import,
        import_progress_1,
        import_progress_2,
        import_progress_3,
        import_progress_4,
    ]
)

# container = Container(widgets=[import_settings])
team_id = None
need_password = True
card = Card(
    title="Select Entities", content=import_settings, lock_message="Select Team from the table"
)
card.lock()


@team_selector.table.click
def show_team_stats(datapoint: Table.ClickedDataPoint):
    global team_id, tf_selector, need_password
    if datapoint.button_name is None:
        return

    with team_selector.progress(message="Preparing team info", total=4) as pbar:
        entities_collapse.set_active_panel(value=[])
        card.loading = True

        start_import.hide()
        output_message.hide()
        team_selector.table.disable()

        row = datapoint.row
        team_id = row[team_selector.TEAM_ID]
        team_name = row[team_selector.TEAM_NAME]
        workspaces_n = row[team_selector.WORKSPACES]
        team_members_n = row[team_selector.TEAM_MEMBERS]
        labeling_jobs_n = row[team_selector.LABELING_JOBS]
        team_files_n = row[team_selector.TEAM_FILES]

        is_team_already_exists = False
        existing_team = g.api.team.get_info_by_name(team_name)
        if existing_team is not None:
            is_team_already_exists = True

        team_selector.progress.set_message("Getting workspaces")
        # Workspaces sync
        workspaces = g.foreign_api.workspace.get_list(team_id)
        ws_items = []
        for ws in workspaces:
            projects = g.foreign_api.project.get_list(ws.id)

            is_ws_already_exists = False
            if is_team_already_exists:
                existing_ws = g.api.workspace.get_info_by_name(existing_team.id, ws.name)
                if existing_ws is not None:
                    is_ws_already_exists = True
                    existing_projects = g.api.project.get_list(existing_ws.id)
                    existing_projects_names = [project.name for project in existing_projects]

            ws_title = ws.name
            if len(projects) == 0:
                ws_title += " (Empty)"

            projects_transfer = Transfer(titles=["Original Team", "Current Team"])
            project_items = []
            existing_project_keys = []
            for project in projects:
                project_item = Transfer.Item(key=project.id, label=project.name)
                project_items.append(project_item)
                if is_ws_already_exists:
                    if project.name in existing_projects_names:
                        if project.type != sly.ProjectType.IMAGES:
                            project_item.disabled = True
                            existing_project_keys.append(project.id)

            projects_transfer.set_items(project_items)
            if len(existing_project_keys) > 0:
                projects_transfer.set_transferred_items(existing_project_keys)
            ws_item = Collapse.Item(name=ws.id, title=ws_title, content=projects_transfer)
            ws_items.append(ws_item)
        ws_collapse.set_items(ws_items)
        pbar.update()

        team_selector.progress.set_message("Getting team members")
        # Team Members sync
        members = g.foreign_api.user.get_team_members(team_id)
        if is_team_already_exists:
            existing_members_names = [
                member.login for member in g.api.user.get_team_members(existing_team.id)
            ]

        new_member_items = []
        existing_member_keys = []
        for member in members:
            member_item = Transfer.Item(key=member.login, label=f"{member.login} ({member.role})")
            new_member_items.append(member_item)
            if is_team_already_exists:
                if member.login in existing_members_names:
                    member_item.disabled = True
                    existing_member_keys.append(member.login)

        members_collapse.set_items(new_member_items)
        if len(existing_member_keys) > 0:
            members_collapse.set_transferred_items(existing_member_keys)

        for member_item in members_collapse._items:
            if not member_item.disabled:
                need_password = True
                break
        pbar.update()

        team_selector.progress.set_message("Getting team files")
        # Team Files
        files: List[FileInfo] = g.foreign_api.file.list(team_id, "/", False, return_type="fileinfo")
        tree_items = []
        for file in files:
            path = file.path
            if file.is_dir:
                path = path.rstrip("/")
            tree_items.append(
                {
                    "path": path,
                    "type": "folder" if file.is_dir else "file",
                    "size": file.sizeb,
                    "id": file.id,
                }
            )
        tf_selector.update_file_tree(files_list=tree_items)

        if len(files_collapse._widgets) > 0:
            files_collapse._widgets.pop()
        files_collapse._widgets.append(tf_selector)
        pbar.update()

        team_selector.progress.set_message("Almost done")
        # Reload widgets
        with contextlib.suppress(Exception):
            files_collapse_r.reload()
        if len(reloadable_container._widgets) > 0:
            reloadable_container._widgets.pop()
        reloadable_container._widgets.append(entities_collapse)
        with contextlib.suppress(Exception):
            reloadable_area.reload()
        ws_collapse.show(), members_collapse.show(), files_collapse.show(), entities_collapse.show()

        card.loading = False
        start_import.show()
        pbar.update()
        card.unlock()


@ws_import_checkbox.value_changed
def ws_import_all(checked: bool):
    if checked:
        ws_collapse.hide()
    else:
        ws_collapse.show()


@tf_selector.path_changed
def file_selector_path_changed(path: str):
    if path == "" or path is None:
        path = "/"
    files: List[FileInfo] = g.foreign_api.file.list(team_id, path, False, return_type="fileinfo")
    tree_items = []
    for file in files:
        path = file.path
        if file.is_dir:
            path = path.rstrip("/")
        tree_items.append(
            {
                "path": path,
                "type": "folder" if file.is_dir else "file",
                "id": file.id,
                "size": file.sizeb,
            }
        )
    tf_selector.update_file_tree(files_list=tree_items)


@need_link_change.value_changed
def change_link(is_checked: bool):
    if is_checked:
        bucket_options.show()
    else:
        bucket_options.hide()


@connect_to_bucket.click
def connect_bucket():
    if connect_to_bucket.text == "Reselect":
        provider_selector.enable()
        bucket_name_input.enable()
        connect_to_bucket.text = "Connect to bucket"
        connect_to_bucket.icon = "zmdi zmdi-cloud"
        connect_to_bucket.plain = False
        return

    provider_selector.disable()
    bucket_name_input.disable()

    bucket_text_info.hide()
    provider = provider_selector.get_value()
    bucket_name = bucket_name_input.get_value()
    if bucket_name == "" or bucket_name is None:
        bucket_text_info.set("Please, enter bucket name", status="error")
        bucket_text_info.show()
        provider_selector.enable()
        bucket_name_input.enable()
        return

    path = f"{provider}://{bucket_name}"
    try:
        files = g.api.remote_storage.list(path, recursive=False, limit=100)
        connect_to_bucket.text = "Reselect"
        connect_to_bucket.icon = "zmdi zmdi-refresh"
        connect_to_bucket.plain = True
        bucket_text_info.set(f"Connected to {path}", status="success")
    except Exception:
        bucket_text_info.set(
            "Can not find bucket or permission denied. Please, check if provider / bucket name is "
            "correct or contact tech support",
            status="error",
        )
        provider_selector.enable()
        bucket_name_input.enable()
        connect_to_bucket.text = "Connect to bucket"
        connect_to_bucket.icon = "zmdi zmdi-cloud"
        connect_to_bucket.plain = False
    bucket_text_info.show()


@start_import.click
def process_import():
    global team_id, need_password
    output_message.hide()

    try:
        # import workspaces
        is_import_all_ws = ws_import_checkbox.is_checked()
        ws_collision_velue = ws_collision.get_value()
        is_fast_mode = ws_options.get_value() == "fast"
        change_link_flag = False
        bucket_path = None
        if is_fast_mode:
            change_link_flag = need_link_change.is_checked()
            bucket_text_value = bucket_text_info.get_value() or ""
            is_bucket_connected = bool(bucket_text_value.startswith("Connected"))
            if change_link_flag and not is_bucket_connected:
                output_message.set(
                    "Please, connect to bucket first or uncheck change link checkbox", status="error"
                )
                output_message.show()
                return
            else:
                bucket_path = f"{provider_selector.get_value()}://{bucket_name_input.get_value()}"

        default_password = team_members_d_password.get_value()
        if need_password:
            if default_password == "" or default_password is None:
                output_message.set("Please, enter default password for new users", status="error")
                output_message.show()
                return

        # pass all validations and start import
        entities_collapse.set_active_panel(value=[])

        import_progress_1.show()
        import_progress_2.show()
        import_progress_3.show()
        import_progress_4.show()

        import_workspaces(
            g.api,
            g.foreign_api,
            team_id,
            ws_collapse,
            import_progress_1,
            import_progress_2,
            import_progress_3,
            import_progress_4,
            is_import_all_ws,
            ws_collision_velue,
            is_fast_mode,
            change_link_flag,
            bucket_path,
        )

        import_progress_2.hide(), import_progress_3.hide(), import_progress_4.hide()
        ##################

        # Team Members
        ignore_users_collision = members_collision.get_value() == "ignore"
        import_team_members(
            g.api,
            g.foreign_api,
            team_id,
            members_collapse,
            default_password,
            import_progress_1,
            ignore_users_collision,
        )
        ##################

        # Team Files
        remote_paths = tf_selector.get_selected_items()
        if len(remote_paths) > 0:
            import_team_files(
                g.api, g.foreign_api, team_id, remote_paths, import_progress_1, import_progress_2
            )
        ##################

        output_message.set(text="Data have been successfully imported.", status="success")
        import_progress_1.hide()
        import_progress_2.hide()
        import_progress_3.hide()
        import_progress_4.hide()
        output_message.show()
    except Exception as e:
        output_message.set(text="Error occurred during import process. Please restart the app.", status="error")
        output_message.show()
        raise e