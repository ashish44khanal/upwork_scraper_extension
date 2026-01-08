import { useState, useEffect } from 'react'
import './App.css'

function App() {
  const [isScraping, setIsScraping] = useState(false)
  const [status, setStatus] = useState<'loading' | 'ready' | 'success' | 'error'>('loading')
  const [error, setError] = useState<string | null>(null)
  console.log(error)
  useEffect(() => {
    const checkStatus = async () => {
      try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
        if (!tab?.id) return

        chrome.tabs.sendMessage(tab.id, { action: 'check_load' }, (response: { isLoaded?: boolean; error?: string } | undefined) => {
          if (chrome.runtime.lastError) {
            console.error(chrome.runtime.lastError)
            setStatus('error')
            setError(chrome.runtime.lastError.message || 'Unknown error') // Set error message
            return
          }
          if (response?.error) {
            setStatus('error')
            setError(response.error)
            return
          }
          if (response?.isLoaded) {
            setStatus('ready')
            setError(null) // Clear error on success
          } else {
            setStatus('loading')
          }
        })
      } catch (err) {
        console.error(err)
        setStatus('error')
      }
    }

    checkStatus()
    const interval = setInterval(checkStatus, 2000)
    return () => clearInterval(interval)
  }, [])

  const handleSubmit = async () => {
    setIsScraping(true)
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
      if (!tab?.id) return

      chrome.tabs.sendMessage(tab.id, { action: 'get_minified_dom' }, async (response: { dom: string; error?: string } | undefined) => {
        if (response?.error) {
          setIsScraping(false)
          setStatus('error')
          setError(response.error)
          return
        }
        
        if (response?.dom) {
          console.log('Minified DOM:', response.dom)
          
          try {
            const apiResponse = await fetch('http://localhost:8000/api/v1/scrape/extract', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({ dom_content: response.dom }),
            });

            if (apiResponse.ok) {
              const data = await apiResponse.json();
              console.log('Extracted Data:', data);
              setIsScraping(false)
              setStatus('success')
            } else {
              throw new Error('API request failed');
            }
          } catch (error) {
            console.error('API Error:', error);
            setIsScraping(false)
            setStatus('error')
          }
        }
      })
    } catch (err) {
      console.error(err)
      setIsScraping(false)
      setStatus('error')
    }
  }

  return (
    <div className="w-80 min-h-[300px] bg-slate-900 text-white p-6 flex flex-col items-center justify-center font-sans">
      <div className="mb-8 text-center">
        <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-emerald-400 bg-clip-text text-transparent">
          Webpage Scraper
        </h1>
        <p className="text-slate-400 text-sm mt-1">Context-Aware Extraction</p>
      </div>

      <div className="flex-1 flex flex-col items-center justify-center w-full">
        {status === 'loading' && (
          <div className="flex flex-col items-center animate-pulse">
            <div className="w-12 h-12 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin mb-4"></div>
            <p className="text-slate-300 font-medium">Webpage isn't fully loaded yet...</p>
          </div>
        )}

        {status === 'ready' && (
          <div className="flex flex-col items-center w-full">
            <div className="w-16 h-16 bg-emerald-500/20 rounded-full flex items-center justify-center mb-4">
              <div className="w-3 h-3 bg-emerald-500 rounded-full animate-ping"></div>
            </div>
            <p className="text-emerald-400 font-semibold mb-6">Ready to Scrape</p>
            <button
              onClick={handleSubmit}
              disabled={isScraping}
              className={`w-full py-3 px-4 rounded-xl font-bold transition-all duration-300 flex items-center justify-center gap-2
                ${isScraping 
                  ? 'bg-slate-800 text-slate-500 cursor-not-allowed' 
                  : 'bg-blue-600 hover:bg-blue-500 active:scale-95 shadow-lg shadow-blue-500/20'}`}
            >
              {isScraping ? (
                <>
                  <div className="w-4 h-4 border-2 border-slate-500 border-t-white rounded-full animate-spin"></div>
                  Processing...
                </>
              ) : (
                'Submit DOM to Scrape'
              )}
            </button>
          </div>
        )}

        {status === 'success' && (
          <div className="flex flex-col items-center text-center">
            <div className="w-16 h-16 bg-emerald-500 rounded-full flex items-center justify-center mb-4 shadow-lg shadow-emerald-500/20">
              <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7"></path>
              </svg>
            </div>
            <p className="text-emerald-400 font-bold text-lg">Success!</p>
            <p className="text-slate-400 text-sm mt-2">Job data extracted and saved</p>
            <div className="flex gap-3 mt-6">
              <button 
                onClick={() => window.close()}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm font-medium transition-colors"
              >
                Close
              </button>
              <button 
                onClick={() => setStatus('ready')}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors"
              >
                Scrape Again
              </button>
            </div>
          </div>
        )}

        {status === 'error' && (
          <div className="flex flex-col items-center text-center">
            <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center mb-4">
              <span className="text-red-500 text-2xl font-bold">!</span>
            </div>
            <p className="text-red-400 font-semibold">
              {error?.includes('Unsupported Platform') ? 'Unsupported Platform' : 
               error?.includes('API Configuration') ? 'API Configuration Error' :
               error?.includes('backend') ? 'Backend Connection Failed' :
               'Error Occurred'}
            </p>
            <p className="text-slate-400 text-xs mt-2 px-4">
              {error || 'An unexpected error occurred. Please try again.'}
            </p>
            <button 
              onClick={() => {
                setStatus('ready')
                setError(null)
              }}
              className="mt-4 px-4 py-2 bg-slate-600 hover:bg-slate-700 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Try Again
            </button>
          </div>
        )}
      </div>

      <div className="mt-8 pt-6 border-t border-slate-800 w-full text-center">
        <p className="text-[10px] text-slate-600 uppercase tracking-widest font-bold">Powered by aashish24.dev</p>
      </div>
    </div>
  )
}

export default App
