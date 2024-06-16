import json
import asyncio
import websockets
import pandas as pd

xls = pd.ExcelFile('../data/graph_data.xlsx')
points_data = pd.read_excel(xls, 'points')
del points_data['Unnamed: 5']
del points_data['Unnamed: 6']

point_id_to_point_data = {
    current.point_id: current.to_dict()
    for idx, current in points_data.iterrows()
}

xls = pd.ExcelFile('../data/graph_data.xlsx')
edges_data = pd.read_excel(xls, 'edges')
del edges_data['Unnamed: 6']
del edges_data['Unnamed: 7']

async def websocket_handler(websocket, path):
    session_id = id(websocket)
    print("A client just connected", session_id)
    await websocket.send(json.dumps({
        'msgtype': 'update',
        'key': 'points_data',
        'value': [
            dict(point_id=point_id, lat=lat, lon=lon, name=name)
            for point_id, lat, lon, name in points_data[['point_id', 'latitude', 'longitude', 'point_name']].values
        ],
    }))
    await websocket.send(json.dumps({
        'msgtype': 'update',
        'key': 'edges_data',
        'value': [
            dict(
                start_point_id=start_point_id, 
                end_point_id=end_point_id, 
                distance=length,
                start_lat=point_id_to_point_data[start_point_id]['latitude'],
                start_lon=point_id_to_point_data[start_point_id]['longitude'],
                end_lat=point_id_to_point_data[end_point_id]['latitude'],
                end_lon=point_id_to_point_data[end_point_id]['longitude'],
            )
            for start_point_id, end_point_id, length in edges_data[['start_point_id', 'end_point_id', 'length']].values
        ],
    }))
    try:
        async for message in websocket:
            print("Received message from client: " + message, session_id)
            # # Process your message here
            # response = "Received your message: " + message
            # await websocket.send(response)
    except websockets.exceptions.ConnectionClosed as e:
        print("A client just disconnected")


async def main():
    async with websockets.serve(websocket_handler, "localhost", 6789):
        print("Server started")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
