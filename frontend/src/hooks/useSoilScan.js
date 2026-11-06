// Photo analysis: pick an image, send it, show the answer.
//
// Moved out of App.jsx. The object URL for the preview is now created and
// revoked together — the old code called createObjectURL on every file change
// and never revoked, so each scan leaked the previous image into memory for the
// lifetime of the tab.

import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'

const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp']

// Matches MAX_IMAGE_BYTES in backend/main.py, with headroom for base64 overhead
// (which inflates a file by about a third).
const MAX_UPLOAD_BYTES = 4_500_000

export function useSoilScan() {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState('')
  const [result, setResult] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const previewUrlRef = useRef('')

  const releasePreview = useCallback(() => {
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current)
      previewUrlRef.current = ''
    }
    setPreview('')
  }, [])

  useEffect(() => () => {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current)
  }, [])

  const selectFile = useCallback(
    (chosen) => {
      setError('')
      setResult('')
      if (!chosen) return

      if (!ACCEPTED_TYPES.includes(chosen.type)) {
        setError('Choose a JPG, PNG or WebP photo. Other formats cannot be analysed.')
        return
      }
      if (chosen.size > MAX_UPLOAD_BYTES) {
        setError(
          `That photo is ${(chosen.size / 1_000_000).toFixed(1)} MB. Photos under ` +
            `${(MAX_UPLOAD_BYTES / 1_000_000).toFixed(0)} MB work best — most phone cameras can shrink automatically.`,
        )
        return
      }

      releasePreview()
      const url = URL.createObjectURL(chosen)
      previewUrlRef.current = url
      setPreview(url)
      setFile(chosen)
    },
    [releasePreview],
  )

  const analyse = useCallback(
    async ({ location, weatherContext }) => {
      if (!file) return
      setLoading(true)
      setError('')
      setResult('')

      try {
        const dataUrl = await new Promise((resolve, reject) => {
          const reader = new FileReader()
          reader.onload = () => resolve(String(reader.result))
          reader.onerror = () => reject(new Error('That photo could not be read. Try taking a new one.'))
          reader.readAsDataURL(file)
        })

        const answer = await api.analysePhoto({
          // The API strips an optional data: prefix, so the whole data URL is
          // fine to send and saves a second round of base64 handling here.
          image: dataUrl,
          mimeType: file.type || 'image/jpeg',
          location: location || 'not provided',
          weatherContext: weatherContext || '',
        })
        setResult(answer?.answer || '')
      } catch (scanError) {
        setError(scanError.message)
      } finally {
        setLoading(false)
      }
    },
    [file],
  )

  const clear = useCallback(() => {
    releasePreview()
    setFile(null)
    setResult('')
    setError('')
  }, [releasePreview])

  return { file, preview, result, error, loading, selectFile, analyse, clear }
}
