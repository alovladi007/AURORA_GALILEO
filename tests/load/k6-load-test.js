/**
 * k6 Load Testing Script for GALILEO Platform
 *
 * Test scenarios:
 * - Baseline load test
 * - Stress test
 * - Spike test
 * - Soak test (endurance)
 *
 * Usage:
 *   k6 run --vus 10 --duration 30s k6-load-test.js
 *   k6 run --env SCENARIO=stress k6-load-test.js
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const apiLatency = new Trend('api_latency');
const successfulRequests = new Counter('successful_requests');

// Configuration
const BASE_URL = __ENV.BASE_URL || 'http://localhost:5050';
const SCENARIO = __ENV.SCENARIO || 'baseline';

// Test scenarios
const scenarios = {
    baseline: {
        executor: 'ramping-vus',
        startVUs: 0,
        stages: [
            { duration: '1m', target: 10 },   // Ramp up to 10 users
            { duration: '3m', target: 10 },   // Stay at 10 users
            { duration: '1m', target: 0 },    // Ramp down
        ],
        gracefulRampDown: '30s',
    },
    stress: {
        executor: 'ramping-vus',
        startVUs: 0,
        stages: [
            { duration: '2m', target: 50 },   // Ramp to 50 users
            { duration: '5m', target: 50 },   // Stay at 50
            { duration: '2m', target: 100 },  // Ramp to 100
            { duration: '5m', target: 100 },  // Stay at 100
            { duration: '2m', target: 200 },  // Ramp to 200
            { duration: '5m', target: 200 },  // Stay at 200
            { duration: '2m', target: 0 },    // Ramp down
        ],
    },
    spike: {
        executor: 'ramping-vus',
        startVUs: 0,
        stages: [
            { duration: '10s', target: 10 },   // Normal load
            { duration: '10s', target: 200 },  // Spike!
            { duration: '30s', target: 200 },  // Stay high
            { duration: '10s', target: 10 },   // Drop
            { duration: '30s', target: 10 },   // Recover
        ],
    },
    soak: {
        executor: 'constant-vus',
        vus: 50,
        duration: '2h',  // Long-running test
    },
};

export const options = {
    scenarios: {
        [SCENARIO]: scenarios[SCENARIO],
    },
    thresholds: {
        // SLO-based thresholds
        'http_req_duration': ['p(95)<300', 'p(99)<500'],  // 95th percentile < 300ms, 99th < 500ms
        'http_req_failed': ['rate<0.01'],   // Error rate < 1%
        'errors': ['rate<0.01'],
    },
};

// Test data
const testOrbits = [
    {
        initial_state: [7000, 0, 0, 0, 7.5, 0],
        duration: 86400,
        time_step: 60
    },
    {
        initial_state: [6800, 0, 0, 0, 7.8, 0],
        duration: 43200,
        time_step: 30
    },
];

export function setup() {
    console.log(`Starting ${SCENARIO} load test against ${BASE_URL}`);

    // Health check
    const healthRes = http.get(`${BASE_URL}/health`);
    check(healthRes, {
        'health check passed': (r) => r.status === 200,
    });

    return { testData: testOrbits };
}

export default function (data) {
    // Mix of different endpoint types

    group('Health & Status', function () {
        const res = http.get(`${BASE_URL}/health`);
        check(res, {
            'health status 200': (r) => r.status === 200,
        });
        apiLatency.add(res.timings.duration);
        errorRate.add(res.status !== 200);
    });

    sleep(1);

    group('Orbit Propagation API', function () {
        const orbit = data.testData[Math.floor(Math.random() * data.testData.length)];

        const payload = JSON.stringify({
            initial_state: orbit.initial_state,
            duration: orbit.duration,
            time_step: orbit.time_step,
        });

        const params = {
            headers: {
                'Content-Type': 'application/json',
            },
            timeout: '60s',
        };

        const res = http.post(`${BASE_URL}/api/orbit/propagate`, payload, params);

        const success = check(res, {
            'propagation status 200': (r) => r.status === 200,
            'has trajectory data': (r) => {
                if (r.status !== 200) return false;
                const body = JSON.parse(r.body);
                return body.times && body.states;
            },
        });

        if (success) {
            successfulRequests.add(1);
        }

        apiLatency.add(res.timings.duration);
        errorRate.add(res.status !== 200);
    });

    sleep(Math.random() * 3 + 1);  // Random sleep 1-4 seconds

    group('Formation Simulation API', function () {
        const payload = JSON.stringify({
            n_satellites: 2,
            baseline_m: 100,
            duration: 3600,
            time_step: 10,
        });

        const params = {
            headers: {
                'Content-Type': 'application/json',
            },
            timeout: '60s',
        };

        const res = http.post(`${BASE_URL}/api/formation/simulate`, payload, params);

        check(res, {
            'formation status 200 or 202': (r) => r.status === 200 || r.status === 202,
        });

        apiLatency.add(res.timings.duration);
        errorRate.add(res.status >= 400);
    });

    sleep(Math.random() * 2 + 1);

    group('ML Model Prediction', function () {
        const payload = JSON.stringify({
            latitude: 40.7128,
            longitude: -74.0060,
            elevation: 0,
        });

        const params = {
            headers: {
                'Content-Type': 'application/json',
            },
        };

        const res = http.post(`${BASE_URL}/api/ml/predict/gravity`, payload, params);

        check(res, {
            'ml prediction status 200': (r) => r.status === 200,
            'has prediction': (r) => {
                if (r.status !== 200) return false;
                const body = JSON.parse(r.body);
                return body.prediction !== undefined;
            },
        });

        apiLatency.add(res.timings.duration);
        errorRate.add(res.status !== 200);
    });

    sleep(1);
}

export function teardown(data) {
    console.log('Load test completed');
    console.log(`Successful requests: ${successfulRequests.value}`);
}

export function handleSummary(data) {
    return {
        'summary.json': JSON.stringify(data, null, 2),
        'stdout': textSummary(data, { indent: ' ', enableColors: true }),
    };
}

function textSummary(data, options) {
    const indent = options.indent || '';
    const enableColors = options.enableColors || false;

    let summary = '\n\n';
    summary += `${indent}Test Results Summary\n`;
    summary += `${indent}${'='.repeat(50)}\n\n`;

    // Overall metrics
    summary += `${indent}Requests:\n`;
    summary += `${indent}  Total: ${data.metrics.http_reqs.values.count}\n`;
    summary += `${indent}  Failed: ${data.metrics.http_req_failed.values.rate * 100}%\n\n`;

    summary += `${indent}Response Time:\n`;
    summary += `${indent}  Min: ${data.metrics.http_req_duration.values.min.toFixed(2)}ms\n`;
    summary += `${indent}  Avg: ${data.metrics.http_req_duration.values.avg.toFixed(2)}ms\n`;
    summary += `${indent}  p95: ${data.metrics.http_req_duration.values['p(95)'].toFixed(2)}ms\n`;
    summary += `${indent}  p99: ${data.metrics.http_req_duration.values['p(99)'].toFixed(2)}ms\n`;
    summary += `${indent}  Max: ${data.metrics.http_req_duration.values.max.toFixed(2)}ms\n\n`;

    summary += `${indent}SLO Compliance:\n`;
    summary += `${indent}  p95 < 300ms: ${data.metrics.http_req_duration.values['p(95)'] < 300 ? 'PASS' : 'FAIL'}\n`;
    summary += `${indent}  p99 < 500ms: ${data.metrics.http_req_duration.values['p(99)'] < 500 ? 'PASS' : 'FAIL'}\n`;
    summary += `${indent}  Error rate < 1%: ${data.metrics.http_req_failed.values.rate < 0.01 ? 'PASS' : 'FAIL'}\n\n`;

    return summary;
}
