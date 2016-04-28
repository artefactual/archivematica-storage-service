from chtest import consumers


channel_routing = {
    "websocket.receive": consumers.ws_message,
    "websocket.connect": consumers.ws_connect,
}
