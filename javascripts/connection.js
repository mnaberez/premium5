class Connection {
    constructor(url, onState, onOpen, onClose) {
        this._ws = new WebSocket(url);
        this._ws.onmessage = (event) => onState(JSON.parse(event.data));
        this._ws.onopen = onOpen;
        this._ws.onclose = onClose;
    }

    send(action, extra) {
        const msg = Object.assign({action: action}, extra || {});
        this._ws.send(JSON.stringify(msg));
    }
}
