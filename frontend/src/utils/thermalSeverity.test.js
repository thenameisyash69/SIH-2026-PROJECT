/**
 * Tests for thermalSeverity.js boundary conditions.
 * Run: node --test frontend/src/utils/thermalSeverity.test.js
 * or via any test runner that supports Node assert.
 */
import assert from 'node:assert'
import { getThermalSeverity } from './thermalSeverity.js'

function check(name, actual, expected) {
  assert.strictEqual(actual, expected, `${name}: expected ${expected}, got ${actual}`)
}

// --- BRIGHTNESS boundaries ---
check('brightness 299.99 -> low', getThermalSeverity(299.99, 0).key, 'low')
check('brightness 300 -> moderate', getThermalSeverity(300, 0).key, 'moderate')
check('brightness 319.99 -> moderate', getThermalSeverity(319.99, 0).key, 'moderate')
check('brightness 320 -> high', getThermalSeverity(320, 0).key, 'high')
check('brightness 339.99 -> high', getThermalSeverity(339.99, 0).key, 'high')
check('brightness 340 -> extreme', getThermalSeverity(340, 0).key, 'extreme')

// --- FRP boundaries ---
check('frp 4.99 -> low', getThermalSeverity(300, 4.99).key, 'low')
check('frp 5 -> moderate', getThermalSeverity(300, 5).key, 'moderate')
check('frp 19.99 -> moderate', getThermalSeverity(300, 19.99).key, 'moderate')
check('frp 20 -> high', getThermalSeverity(300, 20).key, 'high')
check('frp 49.99 -> high', getThermalSeverity(300, 49.99).key, 'high')
check('frp 50 -> extreme', getThermalSeverity(300, 50).key, 'extreme')

// --- Combined severity (higher wins) ---
check('brightness LOW + FRP HIGH => HIGH', getThermalSeverity(299.99, 50).key, 'high')
check('brightness EXTREME + FRP LOW => EXTREME', getThermalSeverity(340, 4.99).key, 'extreme')
check('brightness HIGH + FRP MODERATE => HIGH', getThermalSeverity(320, 10).key, 'high')
check('brightness MODERATE + FRP EXTREME => EXTREME', getThermalSeverity(300, 100).key, 'extreme')

// --- Missing values ---
check('missing brightness + missing FRP => UNKNOWN', getThermalSeverity(null, null).key, 'unknown')
check('missing brightness + FRP present => FRP severity', getThermalSeverity(null, 50).key, 'extreme')
check('brightness present + missing FRP => brightness severity', getThermalSeverity(340, null).key, 'extreme')
check('undefined brightness + undefined FRP => UNKNOWN', getThermalSeverity(undefined, undefined).key, 'unknown')

// --- Labels and colors ---
assert.strictEqual(getThermalSeverity(340, 0).label, 'Extreme')
assert.strictEqual(getThermalSeverity(300, 0).label, 'Moderate')
assert.strictEqual(getThermalSeverity(320, 0).label, 'High')
assert.strictEqual(getThermalSeverity(299, 0).label, 'Weak')
assert.strictEqual(getThermalSeverity(null, null).label, 'Unknown')

assert.strictEqual(getThermalSeverity(340, 0).color, '#E23D3D')
assert.strictEqual(getThermalSeverity(300, 0).color, '#F2C14E')
assert.strictEqual(getThermalSeverity(320, 0).color, '#F2A93B')
assert.strictEqual(getThermalSeverity(299, 0).color, '#3FA796')
assert.strictEqual(getThermalSeverity(null, null).color, '#6B7280')

console.log('All thermalSeverity boundary tests passed.')