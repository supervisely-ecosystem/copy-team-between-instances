import pandas as pd
import supervisely as sly
from supervisely.app.widgets import (
    Card,
    Container,
    Progress,
    Table,
)

TEAM_ID = "id".upper()
TEAM_NAME = "name".upper()
WORKSPACES = "workspaces".upper()
TEAM_MEMBERS = "members".upper()
LABELING_JOBS = "labeling jobs".upper()
TEAM_FILES = "files".upper()
SELECT = "select".upper()

columns = [TEAM_ID, TEAM_NAME, WORKSPACES, TEAM_MEMBERS, LABELING_JOBS, TEAM_FILES, SELECT]
lines = []
table = Table(per_page=5, page_sizes=[5, 10, 15, 30, 50, 100], width="99%")
table.hide()

teams_progress = Progress(hide_on_finish=False)
progress = Progress(hide_on_finish=True)

container = Container([table, progress])
card = Card(title="Select Team", content=container, lock_message="Connect to Supervisely Instance")
card.lock()


def build_table(foreign_api: sly.Api):
    global table, lines
    table.hide()
    lines = []
    table.loading = True
    teams = foreign_api.team.get_list()
    with teams_progress(message="Fetching teams", total=len(teams)) as pbar:
        teams_progress.show()
        for info in teams:
            workspaces = foreign_api.workspace.get_list(info.id)
            team_members = foreign_api.user.get_team_members(info.id)
            jobs = foreign_api.labeling_job.get_list(info.id)
            team_files = foreign_api.file.list(info.id, "/", True)
            lines.append(
                [
                    info.id,
                    info.name or "-",
                    len(workspaces),
                    len(team_members),
                    len(jobs),
                    len(team_files),
                    Table.create_button(SELECT),
                ]
            )
            pbar.update()
    df = pd.DataFrame(lines, columns=columns)
    table.read_pandas(df)
    table.loading = False
    teams_progress.hide()
    table.show()
