import supervisely as sly
from supervisely.app.widgets import Card, Container, Button, Checkbox, Input, Text, Select, Table

import src.globals as g
import src.ui.team_selector as team_selector
import src.ui.entity_selector as entity_selector

sly_address_text = Text("<b>Server Address</b>")
sly_address_input = Input(
    value="",
    placeholder="Enter Supervisely address e.g: https://app.supervisely.com",
    type="text",
)


token_help_slug = "user/settings/tokens"
sly_token_text = Text("<b>API Token</b>")
sly_token_input = Input(
    value="",
    placeholder="Enter Supervisely Token",
    type="password",
)
show_token = Checkbox("Show token", False)

connect_instance = Button("Connect")
connect_message = Text("")

container = Container(
    widgets=[
        sly_address_text,
        sly_address_input,
        sly_token_text,
        sly_token_input,
        show_token,
        connect_message,
        connect_instance,
        team_selector.teams_progress,
    ]
)
card = Card(title="Connect to Supervisely instance", content=container)


@show_token.value_changed
def reveal_token(is_checked: bool):
    if is_checked:
        sly_token_input.set_type(value="text")
    else:
        sly_token_input.set_type(value="password")


@connect_instance.click
def connect():
    connect_message.hide()
    sly_token_input.disable()
    sly_address_input.disable()

    if connect_instance.text == "Reselect":
        show_token.enable()
        team_selector.card.lock()
        entity_selector.card.lock()
        connect_instance.plain = False
        connect_instance.icon = None
        connect_instance.text = "Connect"
        sly_token_input.enable()
        sly_address_input.enable()
        return

    # Validate instance address
    server_address = sly_address_input.get_value()
    if server_address == "" or server_address is None:
        connect_message.set("Supervisely instance address is empty", "error")
        connect_message.show()
        return

    if not server_address.startswith("http://") and not server_address.startswith("https://"):
        connect_message.set(
            "Supervisely instance address should start with http:// or https://",
            "error",
        )
        connect_message.show()
        sly_token_input.enable()
        sly_address_input.enable()
        return
    server_address = server_address.strip(" ").strip("/")

    if server_address == g.api.server_address:
        connect_message.set(
            "Provided Supervisely instance address is the same as the current one.",
            "error",
        )
        connect_message.show()
        sly_token_input.enable()
        sly_address_input.enable()
        return

    # Validate token
    token = sly_token_input.get_value()
    if token == "" or token is None:
        connect_message.set(
            "Token input is empty"
            "\nYou can find your Supervisely token "
            f"<a href='{server_address}/{token_help_slug}'>here</a>.",
            "error",
        )
        connect_message.show()
        sly_token_input.enable()
        sly_address_input.enable()
        return

    if len(token) != 128:
        connect_message.set(
            "Token length must be 128 symbols."
            "\nYou can find your Supervisely token "
            f"<a href='{server_address}/{token_help_slug}'>here</a>.",
            "error",
        )
        connect_message.show()
        sly_token_input.enable()
        sly_address_input.enable()
        return

    # Send request to Supervisely API
    try:
        g.foreign_api = sly.Api(server_address=server_address, token=token)
        user = g.foreign_api.user.get_my_info()
        root = g.api.user.get_info_by_id(1)
    except Exception:
        connect_message.set(
            (
                "Couldn't connect to Supervisely instance. "
                "Check if server address and token are valid."
                "\nYou can find your Supervisely token "
                f"<a href='{server_address}/{token_help_slug}'>here</a>."
            ),
            "error",
        )
        connect_message.show()
        sly_token_input.enable()
        sly_address_input.enable()
        return

    # try:
    #     f_root = g.foreign_api.user.get_info_by_id(1)
    #     if f_root is None:
    #         connect_message.set(
    #             (
    #                 "Provided API token doesn't have access to the root user. "
    #                 "Please, provide token with root access."
    #             ),
    #             "error",
    #         )
    #         connect_message.show()
    #         sly_token_input.enable()
    #         sly_address_input.enable()
    #         return
    # except Exception:
    #     connect_message.set(
    #         (
    #             "Provided API token doesn't have access to the root user. "
    #             "Please, provide token with root access."
    #         ),
    #         "error",
    #     )
    #     connect_message.show()
    #     sly_token_input.enable()
    #     sly_address_input.enable()
    #     return

    team_selector.build_table(g.foreign_api)
    team_selector.card.unlock()
    connect_message.set(f"Connected to {g.foreign_api.server_address} as {user.login}", "success")
    sly_token_input.disable()
    sly_address_input.disable()
    show_token.disable()
    connect_instance.text = "Reselect"
    connect_instance.icon = "zmdi zmdi-rotate-left"
    connect_instance.plain = True
    connect_message.show()
