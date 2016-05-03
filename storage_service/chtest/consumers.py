from channels import Channel
from channels.sessions import enforce_ordering
import locations.api.sword.helpers as helpers


@enforce_ordering(slight=True)
def ws_connect(message):
    pass


@enforce_ordering(slight=True)
def ws_message(message):
    "Echoes messages back to the client"
    message.reply_channel.send(message.content)


def download(message):
    # Write message content, for demo purposes
    with open("/tmp/log.txt", "a") as myfile:
        myfile.write('Message content:' + str(message.content) + "\n")
    helpers._fetch_content(message.content['deposit_uuid'], message.content['objects'], message.content['subdirs'])

    notification = {'notification': 'Download complete'}
    Channel('websocket.receive').send(notification)
