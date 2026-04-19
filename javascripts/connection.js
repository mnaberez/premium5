function createConnection(url, onState, onOpen, onClose) {
    const ws = new WebSocket(url);

    ws.onmessage = function(event) {
        onState(JSON.parse(event.data));
    };

    ws.onopen = function() {
        onOpen();
    };

    ws.onclose = function() {
        onClose();
    };

    function send(action, extra) {
        const msg = Object.assign({action: action}, extra || {});
        ws.send(JSON.stringify(msg));
    }

    return { send: send };
}
