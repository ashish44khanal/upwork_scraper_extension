/**
 * DOM Minifier for LLM Context Preservation
 */
const minifyDOM = (node: Node): string => {
  if (node.nodeType === Node.COMMENT_NODE) return '';
  if (node.nodeType === Node.TEXT_NODE) {
    return node.textContent?.trim().replace(/\s+/g, ' ') || '';
  }

  if (node.nodeType === Node.ELEMENT_NODE) {
    const element = node as HTMLElement;
    const tagName = element.tagName.toLowerCase();

    // Elements to remove entirely
    const blacklistedTags = [
      'script', 'style', 'noscript', 'canvas', 
      'iframe', 'video', 'audio', 'source', 'track'
    ];
    if (blacklistedTags.includes(tagName)) return '';

    // specific handling for head elements
    if (tagName === 'link') {
        // only keep canonical or stylesheet if needed? actually user said minimize payload.
        // usually only canonical is useful for context, or maybe none.
        // let's keep canonical
        if (element.getAttribute('rel') === 'canonical') {
             return `<link rel="canonical" href="${element.getAttribute('href')}" />`;
        }
        return '';
    }

    if (tagName === 'meta') {
        const name = element.getAttribute('name');
        const property = element.getAttribute('property');
        const content = element.getAttribute('content');
        if ((name || property) && content) {
            return `<meta ${name ? `name="${name}"` : `property="${property}"`} content="${content}" />`;
        }
        return '';
    }

    // Attributes to keep
    const whitelistedAttrs = ['href', 'src', 'alt', 'title', 'role', 'name', 'content', 'rel'];
    const attrs = Array.from(element.attributes)
      .filter(attr => whitelistedAttrs.includes(attr.name))
      .map(attr => `${attr.name}="${attr.value}"`)
      .join(' ');

    const attrString = attrs ? ` ${attrs}` : '';
    
    let childrenContent = '';
    element.childNodes.forEach(child => {
      childrenContent += minifyDOM(child);
    });

    // Collapse empty elements unless they are void elements or have specific meaning
    if (!childrenContent.trim() && !['img', 'br', 'hr', 'input', 'meta', 'link'].includes(tagName)) {
        return '';
    }

    return `<${tagName}${attrString}>${childrenContent}</${tagName}>`;
  }

  return '';
};

// Compress string using gzip
const compressString = async (str: string): Promise<string> => {
  // Convert string to Uint8Array
  const encoder = new TextEncoder();
  const data = encoder.encode(str);
  
  // Compress using gzip
  const compressed = await new Response(
    new Blob([data]).stream().pipeThrough(new CompressionStream('gzip'))
  ).blob();
  
  // Convert to base64
  const buffer = await compressed.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
};

chrome.runtime.onMessage.addListener((
    request: { action: string },
    _sender: chrome.runtime.MessageSender,
    sendResponse: (response?: { isLoaded?: boolean; dom?: string; error?: string }) => void
) => {
    // Validate domain
    if (!window.location.hostname.includes('upwork.com')) {
        if (request.action === 'check_load' || request.action === 'get_minified_dom') {
            sendResponse({ error: 'Unsupported Platform - Only supports Upwork job details' });
            return true;
        }
    }

    if (request.action === 'check_load') {
        const isLoaded = document.readyState === 'complete';
        sendResponse({ isLoaded });
        return true;
    }

    if (request.action === 'get_minified_dom') {
        const minified = minifyDOM(document.documentElement);
        // Compress before sending
        compressString(minified).then(compressed => {
            console.log(`Original size: ${minified.length} bytes, Compressed: ${compressed.length} bytes`);
            sendResponse({ dom: compressed });
        }).catch(error => {
            console.error('Compression error:', error);
            sendResponse({ error: 'Failed to compress DOM' });
        });
        return true; // Keep channel open for async response
    }
    
    return false;
});

console.log("DOM Scraper Content Script Loaded");
