#!/bin/sh
B=./bench/bench.py
echo "GROUP 0 Air,Basic,ML,Babylon,cdjs,first-inspector-code-load"
python3 $B run --label js-groups --p "url=http://127.0.0.1:8099/jetstream3.0/index.html?startAutomatically&test=Air,Basic,ML,Babylon,cdjs,first-inspector-code-load" jetstream-js
echo "GROUP 1 multi-inspector-code-load,Box2D,octane-code-load,crypto,delta-blue,earley-boyer"
python3 $B run --label js-groups --p "url=http://127.0.0.1:8099/jetstream3.0/index.html?startAutomatically&test=multi-inspector-code-load,Box2D,octane-code-load,crypto,delta-blue,earley-boyer" jetstream-js
echo "GROUP 2 gbemu,mandreel,navier-stokes,pdfjs,raytrace,regexp-octane"
python3 $B run --label js-groups --p "url=http://127.0.0.1:8099/jetstream3.0/index.html?startAutomatically&test=gbemu,mandreel,navier-stokes,pdfjs,raytrace,regexp-octane" jetstream-js
echo "GROUP 3 richards,splay,FlightPlanner,OfflineAssembler,UniPoker,validatorjs"
python3 $B run --label js-groups --p "url=http://127.0.0.1:8099/jetstream3.0/index.html?startAutomatically&test=richards,splay,FlightPlanner,OfflineAssembler,UniPoker,validatorjs" jetstream-js
echo "GROUP 4 hash-map,doxbee-promise,doxbee-async,ai-astar,gaussian-blur,stanford-crypto-aes"
python3 $B run --label js-groups --p "url=http://127.0.0.1:8099/jetstream3.0/index.html?startAutomatically&test=hash-map,doxbee-promise,doxbee-async,ai-astar,gaussian-blur,stanford-crypto-aes" jetstream-js
echo "GROUP 5 stanford-crypto-pbkdf2,stanford-crypto-sha256,json-stringify-inspector,json-parse-inspector,bigint-noble-ed25519,proxy-mobx"
python3 $B run --label js-groups --p "url=http://127.0.0.1:8099/jetstream3.0/index.html?startAutomatically&test=stanford-crypto-pbkdf2,stanford-crypto-sha256,json-stringify-inspector,json-parse-inspector,bigint-noble-ed25519,proxy-mobx" jetstream-js
echo "GROUP 6 proxy-vue,mobx-startup,jsdom-d3-startup,web-ssr,raytrace-public-class-fields,raytrace-private-class-fields"
python3 $B run --label js-groups --p "url=http://127.0.0.1:8099/jetstream3.0/index.html?startAutomatically&test=proxy-vue,mobx-startup,jsdom-d3-startup,web-ssr,raytrace-public-class-fields,raytrace-private-class-fields" jetstream-js
echo "GROUP 7 typescript-lib,async-fs,sync-fs,lazy-collections,js-tokens,threejs"
python3 $B run --label js-groups --p "url=http://127.0.0.1:8099/jetstream3.0/index.html?startAutomatically&test=typescript-lib,async-fs,sync-fs,lazy-collections,js-tokens,threejs" jetstream-js
echo "GROUP 8 babylonjs-startup-es6,babylonjs-scene-es6,bomb-workers,segmentation,WSL,Sunspider"
python3 $B run --label js-groups --p "url=http://127.0.0.1:8099/jetstream3.0/index.html?startAutomatically&test=babylonjs-startup-es6,babylonjs-scene-es6,bomb-workers,segmentation,WSL,Sunspider" jetstream-js
