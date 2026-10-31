// Preloaded before the test runner and its dependencies. No RPC, DNS or sockets.
import net from 'node:net';
import tls from 'node:tls';
import dns from 'node:dns';
import http from 'node:http';
import https from 'node:https';
import dgram from 'node:dgram';
import { syncBuiltinESMExports } from 'node:module';

const denied = () => { throw new Error('Network access forbidden in BCP contract checks'); };
net.connect = net.createConnection = net.createServer = denied;
net.Socket.prototype.connect = denied;
tls.connect = denied;
http.request = http.get = http.createServer = denied;
https.request = https.get = https.createServer = denied;
dgram.createSocket = denied;
dns.lookup = dns.lookupService = denied;
for (const key of Object.keys(dns)) if (key.startsWith('resolve') && typeof dns[key] === 'function') dns[key] = denied;
for (const key of Object.keys(dns.promises)) if (typeof dns.promises[key] === 'function') dns.promises[key] = denied;
globalThis.fetch = denied;
globalThis.WebSocket = class { constructor() { denied(); } };
syncBuiltinESMExports();
