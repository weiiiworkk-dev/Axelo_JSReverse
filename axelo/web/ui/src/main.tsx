import ReactDOM from 'react-dom/client'
import { App } from './app/App'
import './styles.css'

const rootElement = document.getElementById('app')

if (!rootElement) {
  throw new Error('Unable to find app root')
}

ReactDOM.createRoot(rootElement).render(<App />)
