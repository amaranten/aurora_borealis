import { Feature, Map, View } from 'ol/index.js';
import { OSM, Vector as VectorSource } from 'ol/source.js';
import { Point, LineString } from 'ol/geom.js';
import { Circle as CircleStyle, Fill, Stroke, Style, Text as TextStyle } from 'ol/style';
import { Tile as TileLayer, Vector as VectorLayer } from 'ol/layer.js';
import { useGeographic } from 'ol/proj.js';

const createShortestPathEdge = (start, end) => {
    let [startLon, startLat] = start;
    let [endLon, endLat] = end;

    const deltaLon = endLon - startLon;
    if (Math.abs(deltaLon) > 180) {
        if (deltaLon > 180) {
            endLon -= 360;
        } else if (deltaLon < -180) {
            endLon += 360;
        }
    }
    return new LineString([[startLon, startLat], [endLon, endLat]]);
};

export const element = (tag = 'div', classes = [], styles = {}, parent = null) => {
    const element = document.createElement(tag);
    element.classList.add(...classes);
    for (const [name, value] of Object.entries(styles))
        element.style[name] = value;
    if (parent) parent.appendChild(element);
    return element;
};

export const div = (classes = [], styles = {}, parent = null) => element('div', classes, styles, parent);

export const textnode = (text, parent) => {
    const node = document.createTextNode(text);
    if (parent) parent.appendChild(node);
    return node;
};

export const deep_copy = (obj) => {
    if (obj === null) return null;
    if (typeof obj !== 'object') return obj;
    if (Array.isArray(obj))
        return obj.map(x => deep_copy(x));
    const result = {};
    for (let key in obj) {
        result[key] = deep_copy(obj[key]);
    }
    return result;
};

export const is_deep_equal = (left, right) => {
    if (left === right) return true;
    if (left == null || right == null) return false;
    if (typeof left !== 'object' || typeof right !== 'object') return false;
    if (Object.getPrototypeOf(left) !== Object.getPrototypeOf(right)) return false;
    let keysLeft = Object.keys(left);
    let keysRight = Object.keys(right);
    if (keysLeft.length !== keysRight.length) return false;
    for (let key of keysLeft) {
        if (!keysRight.includes(key) || !is_deep_equal(left[key], right[key])) return false;
    }
    return true;
};

const getWebSocketUrl = () => {
    const host = window.location.host;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${host}/ws/`;
}

export class Application {
    constructor() {
        this.animation_frame_requested = false;
        this.scheduled = {};
        this.old_data = {};
        this.data = { 
            started: true,
            points_data: [],
            edges_data: [],  // Ensure edges_data is included
        };
        this.initWebSocket();
    }

    initWebSocket() {
        const webSocketUrl = getWebSocketUrl();
        this.socket = new WebSocket(webSocketUrl);

        this.socket.addEventListener('open', () => {
            console.log('WebSocket connection established');
            this.socket.send('Hello Server!');
        });

        this.socket.addEventListener('message', event => {
            let data = JSON.parse(event.data);
            if (data.msgtype === 'update') {
                this.data[data.key] = data.value;
                this.update();
            }
        });

        this.socket.addEventListener('close', () => {
            console.log('WebSocket connection closed');
        });

        this.socket.addEventListener('error', error => {
            console.error('WebSocket error:', error);
        });
    }

    sendMessage(message) {
        if (this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(message);
        } else {
            console.log('WebSocket is not open. Unable to send message');
        }
    }

    closeWebSocket() {
        this.socket.close();
    }

    did_change = (names) =>
        (names ?? Object.keys(this.data)).reduce((current, name) => current || !is_deep_equal(this.old_data[name], this.data[name]), false);

    schedule = (tag, f) => {
        if (!this.animation_frame_requested) {
            requestAnimationFrame(() => this.render());
        }
        this.animation_frame_requested = true;
        this.scheduled[tag] = f;
    }

    update = () => {
        if (!this.did_change()) return;

        if (this.did_change(['started', 'points_data', 'edges_data'])) {
            const place = [68.3, 76.2];  // Use the original place coordinates
            useGeographic();
            document.getElementById('map').innerHTML = '';
            console.log(this.data);

            this.map = new Map({
                target: 'map',
                view: new View({
                    center: place,
                    zoom: 4,
                }),
                layers: [
                    new TileLayer({
                        source: new OSM(),
                        wrapX: true,  // Enable wrapping
                    }),
                    new VectorLayer({
                        source: new VectorSource({
                            features: this.data.edges_data.map(edge => {
                                // Use the function to create the shortest path edge
                                const lineString = createShortestPathEdge(
                                    [edge.start_lon, edge.start_lat], 
                                    [edge.end_lon, edge.end_lat]
                                );
                                return new Feature(lineString);
                            })
                        }),
                        style: new Style({
                            stroke: new Stroke({
                                color: '#61cc00',
                                width: 2
                            })
                        }),
                        wrapX: true,
                    }),
                    new VectorLayer({
                        source: new VectorSource({
                            features: this.data.points_data.map((pt) => {
                                const pointFeature = new Feature(new Point([pt.lon, pt.lat]));

                                // Define the style with text (label)
                                const pointStyle = new Style({
                                    image: new CircleStyle({
                                        radius: 4,
                                        fill: new Fill({ color: '#009a00' }),
                                    }),
                                    text: new TextStyle({
                                        font: '12px Calibri,sans-serif',
                                        text: pt.name,  // Assuming each point has a label property
                                        fill: new Fill({ color: '#000' }),
                                        stroke: new Stroke({
                                            color: '#fff', width: 2
                                        }),
                                        offsetY: -15, // Move the label above the point
                                    })
                                });

                                pointFeature.setStyle(pointStyle);
                                return pointFeature;
                            })
                        }),
                    }),
                ],
            });
        }
    }

    render = () => {
        this.animation_frame_requested = false;
        Object.values(this.scheduled).forEach(f => f());
        this.scheduled = {};
    }
};

const app = new Application();

document.addEventListener('DOMContentLoaded', () => {
    app.update();
});
