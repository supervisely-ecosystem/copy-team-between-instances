import os
from typing import List
import supervisely as sly
from supervisely.app.widgets import Progress
from supervisely import TeamInfo
from supervisely.api.user_api import UserInfo
from supervisely.api.role_api import RoleInfo

# Disabled users will be skipped
# Restricted users will be unrestricted


def import_team_members(
    api: sly.Api,
    foreign_api: sly.Api,
    team_id: str,
    members_collapse: sly.app.widgets.Transfer,
    default_password: str,
    progress: Progress,
    ignore_collision: bool,
):
    foreign_team: TeamInfo = foreign_api.team.get_info_by_id(team_id)
    res_team: TeamInfo = api.team.get_info_by_name(foreign_team.name)
    if res_team is None:
        res_team = api.team.create(name=foreign_team.name, description=foreign_team.description)

    existing_members: List[UserInfo] = api.user.get_team_members(team_id=res_team.id)
    existing_members_map = {
        member.login: {"id": member.id, "role": member.role} for member in existing_members
    }

    # incoming_members: List[UserInfo] = foreign_api.user.get_team_members(team_id=foreign_team.id)
    # incoming_members_map = [
    # foreign_api.user.get_info_by_login(member)
    # for member in members_collapse.get_transferred_items()
    # ]
    incoming_users_names = members_collapse.get_transferred_items()
    incoming_users = [
        user
        for user in foreign_api.user.get_team_members(team_id)
        if user.login in incoming_users_names
    ]

    roles_map = {role.role: role.id for role in api.role.get_list()}
    incoming_members = sorted(incoming_users, key=lambda user_info: user_info.role)
    with progress(
        message=f"Import team members from {foreign_team.name}", total=len(incoming_members)
    ) as pbar:
        for incoming_member in incoming_members:
            add_member_to_team(
                api=api,
                team=res_team,
                member=incoming_member,
                default_password=default_password,
                existing_members_map=existing_members_map,
                roles_map=roles_map,
                ignore_collision=ignore_collision,
                pbar=pbar,
            )


def add_member_to_team(
    api: sly.Api,
    team: TeamInfo,
    member: UserInfo,
    default_password: str,
    existing_members_map: dict,
    roles_map: dict,
    ignore_collision: bool,
    pbar,
):
    if member.login in existing_members_map:
        sly.logger.info(f'User: "{member.login}" already exists')
        if ignore_collision:
            pbar.update()
            return
        if existing_members_map[member.login]["role"] != member.role:
            api.user.change_team_role(
                existing_members_map[member.login]["id"], team.id, roles_map[member.role]
            )
            sly.logger.info(f'User: "{member.login}" role has been changed')
    else:
        res_user = api.user.get_info_by_login(member.login)
        if res_user is None:
            res_user = api.user.create(
                login=member.login,
                password=default_password,
                is_restricted=False,
                name=member.name or "",
                email=member.email or "",
            )
        if res_user.disabled:
            sly.logger.info(f'User: "{member.login}" is disabled. User will be ignored')
            pbar.update()
            return
        try:
            api.user.add_to_team_by_login(member.login, team.id, roles_map[member.role])
        except:
            api.user.add_to_team_by_login(member.login, team.id, roles_map["annotator"])

        sly.logger.info(f'User: "{member.login}" has been added to team "{team.name}"')
    pbar.update()
