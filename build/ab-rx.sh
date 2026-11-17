#!/bin/sh
# A/B of the 32-bit RegExp JIT on one build, interleaved per round.
python3 ./bench/bench.py run --label rx-off --p env=JSC_useRegExpJIT=false micro load-wiki wheel-wiki raf-wiki speedometer cold-youtube wheel-youtube
python3 ./bench/bench.py run --label rx-on micro load-wiki wheel-wiki raf-wiki speedometer cold-youtube wheel-youtube
python3 ./bench/bench.py run --label rx-off --p env=JSC_useRegExpJIT=false micro load-wiki wheel-wiki raf-wiki speedometer cold-youtube wheel-youtube
python3 ./bench/bench.py run --label rx-on micro load-wiki wheel-wiki raf-wiki speedometer cold-youtube wheel-youtube
python3 ./bench/bench.py run --label rx-off --p env=JSC_useRegExpJIT=false micro load-wiki wheel-wiki raf-wiki speedometer cold-youtube wheel-youtube
python3 ./bench/bench.py run --label rx-on micro load-wiki wheel-wiki raf-wiki speedometer cold-youtube wheel-youtube
python3 ./bench/bench.py run --label rx-off --p env=JSC_useRegExpJIT=false micro load-wiki wheel-wiki raf-wiki speedometer cold-youtube wheel-youtube
python3 ./bench/bench.py run --label rx-on micro load-wiki wheel-wiki raf-wiki speedometer cold-youtube wheel-youtube
