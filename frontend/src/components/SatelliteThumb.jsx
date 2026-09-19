import { useEffect, useState } from 'react'
import { fetchSatelliteImage } from '../api'

export default function SatelliteThumb({ hotspotId }) {
  const [image, setImage] = useState(null)
  const [status, setStatus] = useState('loading')

  useEffect(() => {
    if (!hotspotId) return
    setStatus('loading')
    fetchSatelliteImage(hotspotId)
      .then((data) => { setImage(data); setStatus('ready') })
      .catch(() => setStatus('error'))
  }, [hotspotId])

  if (status === 'loading') return <div className="satellite satellite--loading">Loading satellite imagery…</div>
  if (status === 'error' || !image) return <div className="satellite satellite--error">Satellite imagery unavailable offline.</div>

  return (
    <div className="satellite">
      <img
        src={image.url}
        alt="Satellite view of hotspot location"
        onError={(e) => { e.target.style.display = 'none' }}
      />
      <p className="satellite__caption">{image.source} · {image.date}</p>
    </div>
  )
}
