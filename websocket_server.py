import json
import asyncio
import websockets
from datetime import datetime
import pandas as pd
import math
import networkx as nx
import pickle as pkl
import numpy as np

with open('../notebooks/edge_times.pkl', 'rb') as handle:
    edge_times = pkl.load(handle)

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


G = macro = nx.Graph()
for i, current in points_data.iterrows():
    current['shifted_longitude'] = current['longitude'] - 20
    if current['shifted_longitude'] < -180:
        current['shifted_longitude'] += 360
    macro.add_node(int(current.point_id), **current.to_dict())


for i, current in edges_data.iterrows():
    current['weight'] = current['length']
    macro.add_edge(int(current.start_point_id), int(current.end_point_id), **current.to_dict())


def format_minutes(total_minutes):
    days = total_minutes // (24 * 60) + 1
    hours = (total_minutes % (24 * 60)) // 60
    minutes = total_minutes % 60 
    return f"Day {days}, {hours:02}:{minutes:02}"

ship_schedules = {}

class TemporalPathfinder:
    def __init__(self, G, duration_function, time_step, n_time_steps, max_time_steps, min_time_steps=0):
        """
        G - это "макро"-граф, который строится выше по данным.
        
        duration_function - см. simple_duration_function
        
        time_step - это квант времени (в минутах)
        
        n_time_steps - максмальный момент времени, в который разрешается отправка корабля 
        (время тут везде измеряется в квантах, т.е. количестве time_step прошедщих с начала)
        
        max_time_steps - максимальный момент времени, в который разрешается прибытие корабля
        """
        self.G = G
        self.time_step = time_step
        self.n_time_steps = n_time_steps
        self.max_time_steps = max_time_steps
        self.duration_function = duration_function
        self.min_time_steps = min_time_steps
        self.tG = self.build_temporal_graph(G)

    def build_temporal_graph(self, G):
        tG = nx.DiGraph()

        for t in range(self.min_time_steps, self.max_time_steps):
            for i, current in points_data.iterrows():
                current['shifted_longitude'] = current.longitude - 20
                if current['shifted_longitude'] < -180:
                    current['shifted_longitude'] += 360
                tG.add_node((t, current.point_id), **current.to_dict())

                if t < self.n_time_steps:
                    for src, dst in G.edges(current.point_id):
                        duration = self.duration_function(src, dst, t)
                        if duration is None:
                            continue
                        t1 = t + duration
                        if t1 > self.max_time_steps:
                            continue
                        if not tG.has_node((t1, dst)):
                            tG.add_node((t1, dst), **G.nodes[dst])
                        tG.add_edge((t, src), (t1, dst), duration=duration, **G.edges[src, dst])
                    
                if t + 1 < self.max_time_steps:
                    src = dst = current.point_id
                    if not tG.has_node((t + 1, dst)):
                        tG.add_node((t + 1, dst), **G.nodes[dst])
                    tG.add_edge((t, src), (t + 1, dst), 
                        id=None,
                        start_point_id=src,
                        end_point_id=src,
                        length=0.,
                        rep_id=None,
                        status=None,
                        weight=0.,
                        duration=1.,
                    )
                    
        for i, current in points_data.iterrows():
            current['shifted_longitude'] = current.longitude - 20
            if current['shifted_longitude'] < -180:
                current['shifted_longitude'] += 360
            tG.add_node((None, current.point_id), **current.to_dict())
            for t in range(self.max_time_steps):
                tG.add_edge((t, current.point_id), (None, current.point_id), duration=0)
            
        return tG

    def shortest_path(self, src, dst, time_start):
        assert self.time_step == 10
        path = nx.shortest_path(self.tG, source=(time_start, src), target=(None, dst), weight='duration')
        for (time, node) in path[:-1]:
            print(f'''{format_minutes(int(time * self.time_step))} ({time}, {time * self.time_step}) - {self.G.nodes[node]["point_name"]} (point {node})''')
        return path


def make_ice_based_duration_function(ship, icebreaker=None, timestep_in_minutes=10):
    def duration_function(start_point_id, end_point_id, start_time_idx):
        if (start_point_id, end_point_id, ship, icebreaker, start_time_idx // 10080 * 10080) not in edge_times:
            start_point_id, end_point_id = end_point_id, start_point_id
        result = edge_times[(start_point_id, end_point_id, ship, icebreaker, start_time_idx // 10080 * 10080)] * 60 // timestep_in_minutes
        if not np.isfinite(result):
            return None
        return result
    return duration_function

def parse_date_time(date_time_str):
    try:
        # Attempt to parse the datetime string
        date_time_obj = datetime.strptime(date_time_str, '%Y-%m-%d %H:%M:%S')
        return date_time_obj
    except ValueError as e:
        # Handle the case where the format does not match
        print(f"Error: {e}")
        return None

class Scheduler:
    def __init__(self, timestep_in_minutes, icebreaker_positions):
        self.point_name_to_point_id = dict(zip(map(str.lower, points_data.point_name), points_data.point_id))
        self.timestep_in_minutes = timestep_in_minutes
        self.current_time = 0

        self.icebreakers = {}
        self.schedule = []

    def schedule_ship(self, ship_name, source_point_id, destination_point_id, departure_time):
        if isinstance(source_point_id, str):
            source_point_id = self.point_name_to_point_id[source_point_id.lower()]
            destination_point_id = self.point_name_to_point_id[destination_point_id.lower()]
        tpf = TemporalPathfinder(G, make_ice_based_duration_function(ship_name, 'Ямал'), time_step=self.timestep_in_minutes, n_time_steps=departure_time + 1008 * 8, max_time_steps=departure_time + 1008 * 8, min_time_steps=departure_time)
        path = tpf.shortest_path(source_point_id, destination_point_id, departure_time)[:-1]
        self.schedule.append({
            'ship': ship_name,
            'schedule': path,
        })
        return path

scheduler = Scheduler(
    timestep_in_minutes=10.,
    icebreaker_positions={
        '50 лет Победы': 27, # Пролив Лонга
        'Ямал': 41, # Рейд Мурманска
        'Таймыр': 16, # Мыс Желания
        'Вайгач': 6, # Победа месторождение
    }
)


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

            data = json.loads(message)
            if data['msgtype'] == 'calculate-schedule':
                try: 
                    start_point_id = data['start_point_id']
                    end_point_id = data['end_point_id']
                    time = parse_date_time(data['departure_time'])
                    ship = data['ship']
                    time = max(0, math.ceil((time - datetime(2022, 3, 3, 0, 0, 0)).total_seconds() / 600.))
                    print('caclulating schedule...', data)
                    result = scheduler.schedule_ship(ship, start_point_id, end_point_id, time)

                    ship_schedules[ship] = result
                    websocket.send(json.dumps({
                        'msgtype': 'update',
                        'key': 'ship_schedules',
                        'value': ship_schedules,
                    }))
                except Exception as exc:
                    print(exc)


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
