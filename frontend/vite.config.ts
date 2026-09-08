import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import net from 'net'

/**
 * Finds the backend automatically instead of assuming port 8000.
 *
 * Port 8000 is frequently unavailable on Windows — Hyper-V, WSL2 and Docker
 * Desktop reserve large TCP ranges, which surfaces as
 * "WinError 10013: An attempt was made to access a socket in a way forbidden
 * by its access permissions". The usual workaround is `uvicorn --port 8080`,
 * and then the frontend keeps proxying to 8000 and every request fails with
 * ECONNREFUSED, showing blank cards with no explanation.
 *
 * This probes the common ports at startup and uses whichever is actually
 * listening. VITE_API_PORT still wins if set explicitly.
 */
const CANDIDATE_PORTS = [8000, 8080, 8001, 5000, 3001]

function isListening(port: number, host = '127.0.0.1', timeout = 300): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = new net.Socket()
    const done = (result: boolean) => {
      socket.destroy()
      resolve(result)
    }
    socket.setTimeout(timeout)
    socket.once('connect', () => done(true))
    socket.once('timeout', () => done(false))
    socket.once('error', () => done(false))
    socket.connect(port, host)
  })
}

async function findBackendPort(explicit?: string): Promise<number> {
  if (explicit) {
    const p = Number(explicit)
    console.log(`\n[api] using VITE_API_PORT=${p}`)
    return p
  }
  for (const port of CANDIDATE_PORTS) {
    if (await isListening(port)) {
      console.log(`\n[api] backend found on port ${port}`)
      return port
    }
  }
  console.log(
    '\n[api] ⚠  No backend found on ports ' + CANDIDATE_PORTS.join(', ') + '.\n' +
    '[api]    Start it with:  cd backend && uvicorn app.main:app --reload\n' +
    '[api]    Defaulting the proxy to 8000.\n')
  return 8000
}

export default defineConfig(async ({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const port = await findBackendPort(env.VITE_API_PORT)
  const target = `http://127.0.0.1:${port}`

  return {
    plugins: [react()],
    server: {
      port: Number(env.VITE_PORT || 5173),
      proxy: {
        '/api': { target, changeOrigin: true },
        '/uploads': { target, changeOrigin: true },
      },
    },
  }
})
