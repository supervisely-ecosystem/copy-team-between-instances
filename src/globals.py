import os
import supervisely as sly
from dotenv import load_dotenv

if sly.is_development():
    load_dotenv("local.env")
    load_dotenv(os.path.expanduser("~/supervisely_assets.env"))

api: sly.Api = sly.Api()
# remove x-task-id header
api.headers.pop("x-task-id", None)

foreign_api: sly.Api = None

team_id = sly.env.team_id()
