// ScanPage — soil scanner and adviser chat on one page, as tabs.
//
// Both features belong to the same user intent: "look at something and get
// advice about it". The soil scanner gives visual observations, the chat
// lets you follow up in words. Tabs keep the page compact and make the
// relationship obvious.
//
// The page is deliberately thin. The scan and chat state live in hooks one level
// up in App.jsx, because switching tabs unmounts these children and the
// conversation has to survive that. The page only translates hook state into the
// flat props SoilScanner and AdviserChat were written against.

import { useCallback, useState } from 'react'
import SoilScanner from '../components/SoilScanner'
import AdviserChat from '../components/AdviserChat'
import Icon from '../components/Icon'

export default function ScanPage({ scan, chat, fieldProfile }) {
  const [activeTab, setActiveTab] = useState('scan') // 'scan' or 'chat'

  // The photo on its own cannot be identified: a leaf looks the same in
  // Limpopo and in the Cape. Passing the field summary is what lets the model
  // say "this looks like blight, common in your area in a wet November" rather
  // than a generic answer.
  const handleScan = useCallback(() => {
    scan.analyse({
      location: fieldProfile?.location?.label,
      weatherContext: fieldProfile?.summary,
    })
  }, [scan, fieldProfile])

  return (
    <main>
      <div className="container scan-page">
        <div className="scan-tabs card">
          <div className="scan-tabs-header" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'scan'}
              className={'scan-tab' + (activeTab === 'scan' ? ' active' : '')}
              onClick={() => setActiveTab('scan')}
            >
              <Icon name="camera" size={17} />
              Field scan
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'chat'}
              className={'scan-tab' + (activeTab === 'chat' ? ' active' : '')}
              onClick={() => setActiveTab('chat')}
            >
              <Icon name="chat" size={17} />
              Ask Nuru
            </button>
          </div>

          <div className="scan-tabs-body">
            {/* Both tabs stay mounted and are hidden with CSS, so a half-written
                question or an analysed photo is not thrown away by a tab click. */}
            <div hidden={activeTab !== 'scan'}>
              <SoilScanner
                scanFile={scan.file}
                scanPreview={scan.preview}
                scanResult={scan.result}
                scanLoading={scan.loading}
                scanError={scan.error}
                onSelectFile={scan.selectFile}
                onScan={handleScan}
                onRemove={scan.clear}
              />
            </div>
            <div hidden={activeTab !== 'chat'}>
              <AdviserChat
                messages={chat.messages}
                messageInput={chat.input}
                chatLoading={chat.loading}
                chatError={chat.error}
                onInputChange={chat.setInput}
                onSend={chat.send}
                onPresetQuestion={chat.send}
              />
            </div>
          </div>
        </div>
      </div>
    </main>
  )
}
