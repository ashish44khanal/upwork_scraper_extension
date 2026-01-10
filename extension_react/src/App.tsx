import { useState, useEffect, useRef, useCallback } from 'react'
import './App.css'

function App() {
  const [isScraping, setIsScraping] = useState(false)
  const [isDownloading, setIsDownloading] = useState(false)
  const [status, setStatus] = useState<'loading' | 'ready' | 'success' | 'error'>('loading')
  const [error, setError] = useState<string | null>(null)
  const statusRef = useRef<'loading' | 'ready' | 'success' | 'error'>(status)
  const intervalRef = useRef<number | null>(null)
  const shouldCheckRef = useRef(true)
  
  // Keep ref in sync with status
  useEffect(() => {
    statusRef.current = status
    // Stop checking when in success or error state
    if (status === 'success' || status === 'error') {
      shouldCheckRef.current = false
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [status])

  // Status checking effect - only runs once on mount
  useEffect(() => {
    if (!shouldCheckRef.current) {
      return
    }

    const checkStatus = async () => {
      // Check if we should continue checking
      if (!shouldCheckRef.current || statusRef.current === 'success' || statusRef.current === 'error') {
        if (intervalRef.current) {
          clearInterval(intervalRef.current)
          intervalRef.current = null
        }
        return
      }

      try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
        if (!tab?.id) return

        chrome.tabs.sendMessage(tab.id, { action: 'check_load' }, (response: { isLoaded?: boolean; error?: string } | undefined) => {
          // Don't update status if we're already in success or error state
          if (!shouldCheckRef.current || statusRef.current === 'success' || statusRef.current === 'error') {
            return
          }

          if (chrome.runtime.lastError) {
            console.error(chrome.runtime.lastError)
            shouldCheckRef.current = false
            setStatus('error')
            setError(chrome.runtime.lastError.message || 'Unknown error')
            return
          }
          if (response?.error) {
            shouldCheckRef.current = false
            setStatus('error')
            setError(response.error)
            return
          }
          if (response?.isLoaded) {
            setStatus('ready')
            setError(null)
          } else {
            setStatus('loading')
          }
        })
      } catch (err) {
        console.error(err)
        const currentStatus = statusRef.current as 'loading' | 'ready' | 'success' | 'error'
        if (currentStatus !== 'success' && currentStatus !== 'error') {
          shouldCheckRef.current = false
          setStatus('error')
        }
      }
    }

    checkStatus()
    intervalRef.current = setInterval(checkStatus, 2000)
    
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, []) // Empty dependency array - only run once on mount

  const handleSubmit = useCallback(async () => {
    setIsScraping(true)
    shouldCheckRef.current = false // Stop status checking during scrape
    
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
      if (!tab?.id) {
        setIsScraping(false)
        shouldCheckRef.current = true
        return
      }

      chrome.tabs.sendMessage(tab.id, { action: 'get_minified_dom' }, async (response: { dom: string; error?: string } | undefined) => {
        if (response?.error) {
          setIsScraping(false)
          setStatus('error')
          setError(response.error)
          shouldCheckRef.current = false
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
              shouldCheckRef.current = false // Keep checking stopped on success
            } else {
              throw new Error('API request failed');
            }
          } catch (error) {
            console.error('API Error:', error);
            setIsScraping(false)
            setStatus('error')
            setError('Failed to scrape. Please try again.')
            shouldCheckRef.current = false
          }
        } else {
          setIsScraping(false)
          shouldCheckRef.current = true
        }
      })
    } catch (err) {
      console.error(err)
      setIsScraping(false)
      setStatus('error')
      setError('An unexpected error occurred.')
      shouldCheckRef.current = false
    }
  }, [])

  const handleDownload = useCallback(async () => {
    // Don't change status on download - keep success state
    setIsDownloading(true)
    try {
      const response = await fetch('http://localhost:8000/api/v1/scrape/download')
      
      if (!response.ok) {
        throw new Error('Failed to download file')
      }

      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'scraped_jobs.json'
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      // Keep status as 'success' - don't change it
    } catch (error) {
      console.error('Download Error:', error)
      // Only show error message, don't change status from success
      // We could show a toast or inline error message instead
      alert('Failed to download file. Please try again.')
    } finally {
      setIsDownloading(false)
    }
  }, [])

  const handleScrapeAgain = useCallback(() => {
    // Reset to ready state and restart checking
    shouldCheckRef.current = true
    setStatus('ready')
    setError(null)
    setIsScraping(false)
    setIsDownloading(false)
  }, [])

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
              disabled={isScraping || isDownloading}
              className={`w-full py-3 px-4 rounded-xl font-bold transition-all duration-300 flex items-center justify-center gap-2 mb-3
                ${isScraping || isDownloading
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
            <button 
              onClick={handleDownload}
              disabled={isScraping || isDownloading}
              className={`w-full py-2 px-4 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2
                ${isScraping || isDownloading
                  ? 'bg-slate-700/50 text-slate-500 cursor-not-allowed'
                  : 'bg-slate-700 hover:bg-slate-600 text-white'}`}
            >
              {isDownloading ? (
                <>
                  <div className="w-4 h-4 border-2 border-slate-500 border-t-white rounded-full animate-spin"></div>
                  Downloading...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path>
                  </svg>
                  Download File
                </>
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
            <div className="flex gap-3 mt-6 w-full">
              <button 
                onClick={handleScrapeAgain}
                disabled={isDownloading}
                className="flex-1 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-emerald-600/50 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors"
              >
                Scrape Again
              </button>
              <button 
                onClick={handleDownload}
                disabled={isDownloading}
                className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-600/50 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2"
              >
                {isDownloading ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    Downloading...
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path>
                    </svg>
                    Download File
                  </>
                )}
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
              onClick={handleScrapeAgain}
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
