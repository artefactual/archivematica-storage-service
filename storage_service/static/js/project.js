

$(document).ready(function() {
    $('.datatable').dataTable();

    function reactKey(evt) {
        if(evt.keyCode==40) {
            document.getElementById('output').innerHTML='it worked';
        }
    }

    $("body").keydown(function(e) {
        if(e.keyCode == 80) { // "p"
            $('.row:first').prepend('<div class="alert alert-info">Upload complete</div>');
        }
    });

    /*
    var ws_scheme = window.location.protocol == "https:" ? "wss" : "ws";
    var socket = new WebSocket(ws_scheme + '://' + window.location.host + '/chat'); // + window.location.pathname);

    socket.onmessage = function(message) {
        var data = JSON.parse(message.data);
        $('body').append('<b>--' + message + '</b>');
    };
    */
} );
