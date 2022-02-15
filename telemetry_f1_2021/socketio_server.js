var amqp = require('amqp'),
    express = require('express'),
    app = express(),
    io = require('socket.io').listen(app, {
        cors: {
          origin: "http://localhost:8000",
          methods: ["GET", "POST"]
        }
    }),
    rabbitMq = amqp.createConnection({ host: '130.61.139.189'});

app.configure(function () {
   app.use(express.static(__dirname + '/public'));
   app.use(express.errorHandler({ dumpExceptions: true, showStack: true }));
});

rabbitMq.on('ready', function () {
   io.sockets.on('connection', function (socket) {
      var queue = rabbitMq.queue('PacketMotionData');

      queue.bind('#'); // all messages

      queue.subscribe(function (message) {
         socket.emit('PacketMotionData', message);
      });

      PacketCarTelemetryData
   });
});

app.listen(8080);



