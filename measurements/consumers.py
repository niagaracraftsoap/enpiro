from channels.generic.websocket import AsyncJsonWebsocketConsumer


class ReadingConsumer(AsyncJsonWebsocketConsumer):
    group_name = "environmental_readings"

    async def connect(self):
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def reading_created(self, event):
        await self.send_json(event["reading"])

