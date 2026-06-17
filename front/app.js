// CivicAssist.IA Frontend Client Application
document.addEventListener("DOMContentLoaded", () => {
  // Application State
  let currentDomain = "all";
  let chatHistory = []; // Tracks full session history {role: 'user'|'model', content: '...'}
  let serverConfig = {
    total_documents: 0,
    domain_counts: { antai: 0, impots: 0, "service-public": 0 },
    server_api_key_configured: false
  };

  // DOM Cache
  const chatContainer = document.getElementById("chat-container");
  const chatInput = document.getElementById("chat-input");
  const btnSendMessage = document.getElementById("btn-send-message");
  const welcomeScreen = document.getElementById("welcome-screen");
  
  const statAntaiCount = document.getElementById("stat-antai-count");
  const statImpotsCount = document.getElementById("stat-impots-count");
  const statSpCount = document.getElementById("stat-sp-count");
  
  const geminiKeyInput = document.getElementById("gemini-key-input");
  const btnSaveKey = document.getElementById("btn-save-key");
  const apiStatusDot = document.getElementById("api-status-dot");
  const apiStatusText = document.getElementById("api-status-text");
  
  const aiConnectionBadge = document.getElementById("ai-connection-badge");
  const activeDomainTitle = document.getElementById("active-domain-title");
  const activeDomainSubtitle = document.getElementById("active-domain-subtitle");
  
  const filterBtns = document.querySelectorAll(".filter-btn");
  const suggestionCards = document.querySelectorAll(".suggestion-card");

  // Domain descriptions for premium top header transitions
  const DOMAIN_INFO = {
    all: {
      title: "Portail d'Assistance Administrative Unifié",
      subtitle: "Assistant intelligent RAG alimenté par la base de données de l'État"
    },
    antai: {
      title: "Assistance Infractions & PV (ANTAI)",
      subtitle: "Contestations, amendes forfaitaires, amendes majorées, permis et désignations"
    },
    impots: {
      title: "Assistance Fiscale & Impôts",
      subtitle: "Déclarations de revenus, coordonnées bancaires RIB, étalements de paiements et recours"
    },
    "service-public": {
      title: "Mises en demeure & Logement (Service-Public)",
      subtitle: "Baux d'habitation, demandes de logement social HLM et litiges locatifs"
    }
  };

  // 1. Initialize PWA Key from Local Storage
  const savedKey = localStorage.getItem("gemini_api_key");
  if (savedKey) {
    geminiKeyInput.value = savedKey;
  }

  // Update System connection badges
  function updateConnectionBadge() {
    const hasClientKey = !!localStorage.getItem("gemini_api_key");
    const hasServerKey = serverConfig.server_api_key_configured;
    
    if (hasClientKey || hasServerKey) {
      aiConnectionBadge.className = "connection-status-pill";
      aiConnectionBadge.innerHTML = "<span>Assistant IA Actif</span>";
      
      apiStatusDot.className = "status-dot active";
      apiStatusText.textContent = hasClientKey ? "Clé Locale" : "Clé Serveur";
      apiStatusText.style.color = "var(--accent-green)";
    } else {
      aiConnectionBadge.className = "connection-status-pill warning";
      aiConnectionBadge.innerHTML = "<span>Mode Recherche Locale</span>";
      
      apiStatusDot.className = "status-dot warning";
      apiStatusText.textContent = "Simulé";
      apiStatusText.style.color = "#f2c94c";
    }
  }

  // 2. Fetch Server Config and stats on startup
  async function loadConfig() {
    try {
      const res = await fetch("/api/config");
      if (!res.ok) throw new Error("Could not fetch config");
      serverConfig = await res.json();
      
      // Update UI Stats Counters with animation
      animateCounter(statAntaiCount, serverConfig.domain_counts.antai || 0);
      animateCounter(statImpotsCount, serverConfig.domain_counts.impots || 0);
      animateCounter(statSpCount, serverConfig.domain_counts["service-public"] || 0);
      
      updateConnectionBadge();
    } catch (e) {
      console.error("Config fetch error:", e);
      // Mock stats values if server is offline
      statAntaiCount.textContent = "163";
      statImpotsCount.textContent = "73";
      statSpCount.textContent = "209";
    }
  }

  function animateCounter(element, targetValue) {
    let current = 0;
    const duration = 800; // ms
    const stepTime = Math.max(Math.floor(duration / targetValue), 15);
    const step = Math.ceil(targetValue / (duration / stepTime));
    
    const timer = setInterval(() => {
      current += step;
      if (current >= targetValue) {
        element.textContent = targetValue;
        clearInterval(timer);
      } else {
        element.textContent = current;
      }
    }, stepTime);
  }

  // 3. Save API Key Securely locally
  btnSaveKey.addEventListener("click", () => {
    const key = geminiKeyInput.value.trim();
    if (key) {
      localStorage.setItem("gemini_api_key", key);
      showNotification("Clé API enregistrée localement !", "success");
    } else {
      localStorage.removeItem("gemini_api_key");
      showNotification("Clé supprimée, retour au mode recherche locale", "info");
    }
    updateConnectionBadge();
  });

  // 4. Handle Domain Quick-Filters
  filterBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      filterBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      
      currentDomain = btn.dataset.domain;
      
      // Smoothly update header labels
      const info = DOMAIN_INFO[currentDomain] || DOMAIN_INFO.all;
      
      activeDomainTitle.style.opacity = 0;
      activeDomainSubtitle.style.opacity = 0;
      
      setTimeout(() => {
        activeDomainTitle.textContent = info.title;
        activeDomainSubtitle.textContent = info.subtitle;
        activeDomainTitle.style.opacity = 1;
        activeDomainSubtitle.style.opacity = 1;
      }, 150);
    });
  });

  // 5. Connect Suggestion Cards
  suggestionCards.forEach(card => {
    card.addEventListener("click", () => {
      const query = card.dataset.query;
      const domain = card.dataset.domain;
      
      // Activate filter button
      const filterBtn = document.getElementById(`btn-filter-${domain === "service-public" ? "sp" : domain}`);
      if (filterBtn) filterBtn.click();
      
      // Send question
      chatInput.value = query;
      handleSendMessage();
    });
  });

  // 6. Typing Indicator UI
  function showTypingIndicator() {
    const indicator = document.createElement("div");
    indicator.className = "typing-indicator";
    indicator.id = "chat-typing-indicator";
    indicator.innerHTML = `
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
    `;
    chatContainer.appendChild(indicator);
    scrollToBottom();
  }

  function removeTypingIndicator() {
    const indicator = document.getElementById("chat-typing-indicator");
    if (indicator) {
      indicator.remove();
    }
  }

  // 7. Markdown formatter for Gemini RAG
  function formatMarkdown(text) {
    if (!text) return "";
    
    let html = text;
    
    // Safety escape HTML tags to avoid XSS injections
    html = html.replace(/</g, "&lt;").replace(/>/g, "&gt;");
    
    // Headers: ### Title
    html = html.replace(/^### (.*?)$/gm, "<h3>$1</h3>");
    html = html.replace(/^## (.*?)$/gm, "<h3>$1</h3>");
    html = html.replace(/^# (.*?)$/gm, "<h3>$1</h3>");
    
    // Bold: **text**
    html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    
    // Bullet lists: - item or * item
    html = html.replace(/^\s*[-*]\s+(.*?)$/gm, "<li>$1</li>");
    // Wrap consecutive list items in <ul>
    html = html.replace(/(<li>.*?<\/li>)/gs, "<ul>$1</ul>");
    // Clean up duplicate <ul> wrappers
    html = html.replace(/<\/ul>\s*<ul>/g, "");
    
    // Links: [label](url)
    html = html.replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    
    // Line breaks
    html = html.replace(/\n/g, "<br>");
    // Clean up excessive double line breaks
    html = html.replace(/(<br>\s*){2,}/g, "<br><br>");
    
    return html;
  }

  // 8. Add Message to DOM
  function appendMessage(role, text, sources = [], mode = "") {
    // Hide welcome panel on first message
    if (welcomeScreen.style.display !== "none") {
      welcomeScreen.style.display = "none";
    }

    const messageDiv = document.createElement("div");
    messageDiv.className = `message ${role === "user" ? "user" : "assistant"}`;
    
    const avatarDiv = document.createElement("div");
    avatarDiv.className = "avatar";
    avatarDiv.textContent = role === "user" ? "U" : "CA";
    
    const bubbleDiv = document.createElement("div");
    bubbleDiv.className = "message-bubble";
    
    // Format Text
    if (role === "user") {
      bubbleDiv.textContent = text;
    } else {
      bubbleDiv.innerHTML = formatMarkdown(text);
      
      // Append Source Drawer if sources exist
      if (sources && sources.length > 0) {
        const drawer = document.createElement("div");
        drawer.className = "sources-drawer";
        drawer.innerHTML = `
          <div class="sources-header">
            <span>📚 Documents Officiels Référants</span>
          </div>
        `;
        
        const listContainer = document.createElement("div");
        listContainer.className = "sources-list";
        
        sources.forEach(src => {
          const tag = document.createElement("a");
          tag.className = "source-tag";
          tag.href = src.url;
          tag.target = "_blank";
          tag.rel = "noopener noreferrer";
          
          let domainEmoji = "⚖️";
          if (src.domain === "antai") domainEmoji = "🚗";
          if (src.domain === "impots") domainEmoji = "💶";
          
          tag.innerHTML = `<span>${domainEmoji}</span> <strong>${src.question || src.titre || "Fiche Technique"}</strong>`;
          listContainer.appendChild(tag);
        });
        
        drawer.appendChild(listContainer);
        bubbleDiv.appendChild(drawer);
      }
    }
    
    messageDiv.appendChild(avatarDiv);
    messageDiv.appendChild(bubbleDiv);
    
    chatContainer.appendChild(messageDiv);
    scrollToBottom();
  }

  function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }

  // 9. Send Message Core API handler
  async function handleSendMessage() {
    const queryText = chatInput.value.trim();
    if (!queryText) return;
    
    // Clear input
    chatInput.value = "";
    
    // Append user question
    appendMessage("user", queryText);
    
    // Push to local conversation history state
    chatHistory.push({ role: "user", content: queryText });
    
    // Show typing state
    showTypingIndicator();
    
    try {
      const payload = {
        query: queryText,
        domain: currentDomain,
        history: chatHistory,
        apiKey: localStorage.getItem("gemini_api_key")
      };
      
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      
      if (!res.ok) throw new Error("API call error");
      const data = await res.json();
      
      removeTypingIndicator();
      
      // Append AI Response
      appendMessage("assistant", data.answer, data.sources, data.mode);
      
      // Push response to history
      chatHistory.push({ role: "model", content: data.answer });
      
    } catch (e) {
      console.error(e);
      removeTypingIndicator();
      appendMessage("assistant", "⚠️ Une erreur de connexion est survenue. Veuillez vérifier que le serveur FastAPI est actif et réessayez.");
    }
  }

  // Bind message sending triggers
  btnSendMessage.addEventListener("click", handleSendMessage);
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      handleSendMessage();
    }
  });

  // Custom visual notification prompt
  function showNotification(message, type = "info") {
    const notification = document.createElement("div");
    notification.style.position = "fixed";
    notification.style.bottom = "24px";
    notification.style.right = "24px";
    notification.style.background = type === "success" ? "var(--accent-green)" : "var(--accent-blue)";
    notification.style.color = "#000";
    notification.style.fontWeight = "700";
    notification.style.padding = "12px 24px";
    notification.style.borderRadius = "12px";
    notification.style.boxShadow = "var(--glass-shadow)";
    notification.style.zIndex = "100";
    notification.style.fontFamily = "var(--font-sans)";
    notification.style.fontSize = "0.85rem";
    notification.style.opacity = "0";
    notification.style.transform = "translateY(20px)";
    notification.style.transition = "all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1)";
    
    document.body.appendChild(notification);
    notification.textContent = message;
    
    // Trigger animation
    setTimeout(() => {
      notification.style.opacity = "1";
      notification.style.transform = "translateY(0)";
    }, 50);
    
    // Auto remove
    setTimeout(() => {
      notification.style.opacity = "0";
      notification.style.transform = "translateY(20px)";
      setTimeout(() => notification.remove(), 300);
    }, 3000);
  }

  // Load configuration and trigger statistics
  loadConfig();
});
