export function createSSEParser() {
  let buffer = ''

  return function parse(chunk) {
    buffer += chunk
    const events = []
    let boundaryIndex

    while ((boundaryIndex = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, boundaryIndex)
      buffer = buffer.slice(boundaryIndex + 2)
      const event = parseEvent(raw)
      if (event) {
        events.push(event)
      }
    }

    return events
  }
}

function parseEvent(raw) {
  let event = 'message'
  const dataLines = []

  for (const line of raw.split('\n')) {
    const trimmed = line.trim()
    if (trimmed.startsWith('event:')) {
      event = trimmed.slice('event:'.length).trim()
    } else if (trimmed.startsWith('data:')) {
      dataLines.push(trimmed.slice('data:'.length).trim())
    }
  }

  if (dataLines.length === 0) {
    return null
  }

  const dataText = dataLines.join('\n')
  let data
  try {
    data = JSON.parse(dataText)
  } catch {
    data = dataText
  }

  return { event, data }
}
