/**
 * TradingView-Grade Color System
 */

export const TV = {
  bg: {
    primary: '#131722',
    secondary: '#1e222d',
    tertiary: '#2a2e39',
    hover: '#363a45',
  },
  text: {
    primary: '#d1d4dc',
    secondary: '#787b86',
    tertiary: '#434651',
  },
  border: {
    primary: 'rgba(255, 255, 255, 0.1)',
    secondary: 'rgba(255, 255, 255, 0.05)',
  },
  bull: {
    primary: '#26a69a',
    bright: '#22ab94',
    muted: 'rgba(38, 166, 154, 0.2)',
  },
  bear: {
    primary: '#ef5350',
    bright: '#f23645',
    muted: 'rgba(239, 83, 80, 0.2)',
  },
  neutral: {
    primary: '#787b86',
  },
  blue: {
    primary: '#2962ff',
  },
  orange: {
    primary: '#ff9800',
  },
} as const

// Fibonacci level colors — matches Kirk's TradingView Auto Fib Retracement
export const FIB_COLORS: Record<number, string> = {
  0:     '#FFFFFF',   // white — anchor (ZERO)
  0.236: '#808080',   // 50% white — retracement
  0.382: '#808080',   // 50% white — retracement
  0.5:   '#FF9800',   // orange — pivot
  0.618: '#808080',   // 50% white — retracement
  0.786: '#808080',   // 50% white — retracement
  1.0:   '#FFFFFF',   // white — anchor (1)
  1.236: '#4CAF50',   // green — TARGET 1
  1.618: '#4CAF50',   // green — TARGET 2
  2.0:   '#4CAF50',   // green — TARGET 3
}

export default TV
