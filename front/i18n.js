(() => {
  const STORAGE_KEY = "simplifia_language";
  const DEV_MODE_KEY = "simplifia_dev_mode";
  const ANALYSIS_RESULT_STORAGE_KEY = "simplifia_image_analysis";
  const WINDOW_NAME_STATE_PREFIX = "simplifia:";
  const LANGUAGE_QUERY_PARAM = "lang";
  const DEV_QUERY_PARAM = "dev";
  const IMAGE_ANALYSIS_ENDPOINT =
    window.location.protocol === "http:" || window.location.protocol === "https:"
      ? `${window.location.origin}/api/image`
      : "http://127.0.0.1:8000/api/image";
  const DEFAULT_LANGUAGE = "fr";
  const RTL_LANGUAGES = new Set(["ar"]);
  const LANGUAGE_NAMES = {
    fr: "Français",
    en: "English",
    es: "Español",
    ar: "العربية"
  };
  const TRANSLATIONS = {
    fr: {
      common: {
        devMode: "Mode dev"
      },
      index: {
        browserTitle: "Simplifia",
        voiceGuidance: "Guidage audio spatialisé",
        intro: "Sélectionnez une méthode pour analyser et simplifier votre document officiel.",
        takePhoto: "Prendre en photo",
        photoUploading: "Analyse de la photo...",
        photoUploadError: "L'envoi de la photo a échoué. Veuillez réessayer.",
        photoResponseError: "Le service d'analyse a renvoyé une réponse invalide.",
        pasteText: "Coller un texte",
        privacyNote: "Anonyme et sans sauvegarde",
        navHome: "Accueil",
        navScanners: "Scanners",
        navHelp: "Aide",
        footerLegal: "Mentions légales",
        footerAccessibility: "Accessibilité",
        footerPrivacy: "Données personnelles"
      },
      loader: {
        browserTitle: "Simplifia",
        title: "Simplifia",
        subtitle: "Traitement sécurisé de votre document administratif.",
        step1: "Lecture et vérification du document",
        step2: "Protection des données personnelles",
        step3: "Préparation de la synthèse",
        secureConnection: "Service sécurisé conforme aux exigences administratives"
      },
      second: {
        browserTitle: "Simplifia",
        headerTitle: "Simplifia",
        summaryLabel: "Résumé simplifié de votre document",
        documentTitle: "Avis de mise en demeure",
        dynamicDocumentTitle: "Analyse du document",
        problemTitle: "Le problème",
        analysisTitle: "Analyse simplifiée",
        problemBody: "L'administration indique qu'il manque des documents justificatifs pour finaliser votre dossier d'aide au logement pour l'année en cours. Sans ces documents, vos droits pourraient être suspendus.",
        solutionTitle: "La solution",
        solutionBody: "Vous devez envoyer la copie de votre dernier avis d'imposition et une quittance de loyer récente datant de moins de 3 mois.",
        deadlineTitle: "Le délai",
        deadlineIntro: "Vous avez jusqu'au",
        deadlineDate: "15 Octobre 2024",
        deadlineSuffix: "pour fournir ces documents.",
        deadlineBadge: "Action requise rapidement",
        nextSteps: "Voir les démarches"
      },
      three: {
        browserTitle: "Simplifia",
        headerTitle: "Simplifia",
        replyTemplateTitle: "Modèle de réponse",
        dynamicContentTitle: "Simplification du document",
        replyTemplateBody: "Madame, Monsieur,\n\nSuite à votre courrier en date du [Date], je vous informe que les documents demandés ont bien été téléversés sur mon espace personnel.\n\nJe reste à votre entière disposition pour tout complément d'information.\n\nCordialement,\n[Votre Nom]",
        copyButton: "Copier",
        copyFeedback: "Texte copié dans le presse-papiers.",
        helpTitle: "Besoin d'aide en personne ?",
        openUntil: "Ouvert jusqu'à 17h00",
        directions: "S'y rendre"
      }
    },
    en: {
      common: {
        devMode: "Dev mode"
      },
      index: {
        browserTitle: "Simplifia",
        voiceGuidance: "Spatial audio guidance",
        intro: "Choose a method to analyse and simplify your official document.",
        takePhoto: "Take a photo",
        photoUploading: "Analysing photo...",
        photoUploadError: "Photo upload failed. Please try again.",
        photoResponseError: "The analysis service returned an invalid response.",
        pasteText: "Paste text",
        privacyNote: "Anonymous and not stored",
        navHome: "Home",
        navScanners: "Scans",
        navHelp: "Help",
        footerLegal: "Legal notice",
        footerAccessibility: "Accessibility",
        footerPrivacy: "Personal data"
      },
      loader: {
        browserTitle: "Simplifia",
        title: "Simplifia",
        subtitle: "Your administrative document is being processed securely.",
        step1: "Document reading and verification",
        step2: "Personal data protection",
        step3: "Preparing a clear and reliable summary",
        secureConnection: "Secure service aligned with administrative standards"
      },
      second: {
        browserTitle: "Simplifia",
        headerTitle: "Simplifia",
        summaryLabel: "Plain-language summary of your document",
        documentTitle: "Formal notice",
        dynamicDocumentTitle: "Document analysis",
        problemTitle: "The issue",
        analysisTitle: "Plain-language analysis",
        problemBody: "The administration indicates that supporting documents are missing to finalise your housing assistance file for the current year. Without these documents, your entitlements may be suspended.",
        solutionTitle: "The solution",
        solutionBody: "You must send a copy of your latest tax notice and a recent rent receipt dated less than 3 months ago.",
        deadlineTitle: "The deadline",
        deadlineIntro: "You have until",
        deadlineDate: "15 October 2024",
        deadlineSuffix: "to submit these documents.",
        deadlineBadge: "Action required soon",
        nextSteps: "See next steps"
      },
      three: {
        browserTitle: "Simplifia",
        headerTitle: "Simplifia",
        replyTemplateTitle: "Reply template",
        dynamicContentTitle: "Document simplification",
        replyTemplateBody: "Dear Sir or Madam,\n\nFollowing your letter dated [Date], I confirm that the requested documents have been uploaded to my personal account.\n\nI remain at your disposal for any additional information.\n\nYours faithfully,\n[Your Name]",
        copyButton: "Copy",
        copyFeedback: "Text copied to the clipboard.",
        helpTitle: "Need in-person help?",
        openUntil: "Open until 5:00 pm",
        directions: "Get directions"
      }
    },
    es: {
      common: {
        devMode: "Modo dev"
      },
      index: {
        browserTitle: "Simplifia",
        voiceGuidance: "Guía de audio espacial",
        intro: "Seleccione un método para analizar y simplificar su documento oficial.",
        takePhoto: "Tomar una foto",
        photoUploading: "Analizando la foto...",
        photoUploadError: "El envío de la foto falló. Inténtelo de nuevo.",
        photoResponseError: "El servicio de análisis devolvió una respuesta no válida.",
        pasteText: "Pegar un texto",
        privacyNote: "Anónimo y sin guardar",
        navHome: "Inicio",
        navScanners: "Escaneos",
        navHelp: "Ayuda",
        footerLegal: "Avisos legales",
        footerAccessibility: "Accesibilidad",
        footerPrivacy: "Datos personales"
      },
      loader: {
        browserTitle: "Simplifia",
        title: "Simplifia",
        subtitle: "Tratamiento seguro de su documento administrativo.",
        step1: "Lectura y verificación del documento",
        step2: "Protección de los datos personales",
        step3: "Preparación de un resumen",
        secureConnection: "Servicio seguro conforme a los requisitos administrativos"
      },
      second: {
        browserTitle: "Simplifia",
        headerTitle: "Simplifia",
        summaryLabel: "Resumen simplificado de su documento",
        documentTitle: "Requerimiento formal",
        dynamicDocumentTitle: "Análisis del documento",
        problemTitle: "El problema",
        analysisTitle: "Análisis simplificado",
        problemBody: "La administración indica que faltan documentos justificativos para finalizar su expediente de ayuda a la vivienda del año en curso. Sin estos documentos, sus derechos podrían suspenderse.",
        solutionTitle: "La solución",
        solutionBody: "Debe enviar una copia de su último aviso fiscal y un recibo de alquiler reciente con menos de 3 meses de antigüedad.",
        deadlineTitle: "El plazo",
        deadlineIntro: "Tiene hasta el",
        deadlineDate: "15 de octubre de 2024",
        deadlineSuffix: "para presentar estos documentos.",
        deadlineBadge: "Acción requerida pronto",
        nextSteps: "Ver trámites"
      },
      three: {
        browserTitle: "Simplifia",
        headerTitle: "Simplifia",
        replyTemplateTitle: "Modelo de respuesta",
        dynamicContentTitle: "Simplificación del documento",
        replyTemplateBody: "Señora, Señor:\n\nTras su carta de fecha [Fecha], le informo de que los documentos solicitados ya se han cargado en mi espacio personal.\n\nQuedo a su disposición para cualquier información adicional.\n\nAtentamente,\n[Su nombre]",
        copyButton: "Copiar",
        copyFeedback: "Texto copiado al portapapeles.",
        helpTitle: "¿Necesita ayuda en persona?",
        openUntil: "Abierto hasta las 17:00",
        directions: "Cómo llegar"
      }
    },
    ar: {
      common: {
        devMode: "وضع التطوير"
      },
      index: {
        browserTitle: "Simplifia",
        voiceGuidance: "إرشاد صوتي مكاني",
        intro: "اختر طريقة لتحليل مستندك الرسمي وتبسيطه.",
        takePhoto: "التقاط صورة",
        photoUploading: "جارٍ تحليل الصورة...",
        photoUploadError: "فشل إرسال الصورة. يُرجى المحاولة مرة أخرى.",
        photoResponseError: "أعادَت خدمة التحليل استجابة غير صالحة.",
        pasteText: "لصق نص",
        privacyNote: "مجهول ومن دون حفظ",
        navHome: "الرئيسية",
        navScanners: "المسح",
        navHelp: "المساعدة",
        footerLegal: "الإشعارات القانونية",
        footerAccessibility: "إمكانية الوصول",
        footerPrivacy: "البيانات الشخصية"
      },
      loader: {
        browserTitle: "Simplifia",
        title: "Simplifia",
        subtitle: "تتم معالجة مستندك الإداري عبر خدمة آمنة.",
        step1: "قراءة المستند والتحقق منه",
        step2: "حماية البيانات الشخصية",
        step3: "إعداد ملخص واضح وموثوق",
        secureConnection: "خدمة آمنة متوافقة مع المتطلبات الإدارية"
      },
      second: {
        browserTitle: "Simplifia",
        headerTitle: "Simplifia",
        summaryLabel: "ملخص مبسط لمستندك",
        documentTitle: "إنذار رسمي",
        dynamicDocumentTitle: "تحليل المستند",
        problemTitle: "المشكلة",
        analysisTitle: "تحليل مبسط",
        problemBody: "تشير الإدارة إلى وجود مستندات داعمة ناقصة لاستكمال ملف مساعدة السكن الخاص بك للسنة الحالية. ومن دون هذه المستندات قد يتم تعليق حقوقك.",
        solutionTitle: "الحل",
        solutionBody: "يجب عليك إرسال نسخة من آخر إشعار ضريبي وإيصال إيجار حديث لا يتجاوز عمره ثلاثة أشهر.",
        deadlineTitle: "المهلة",
        deadlineIntro: "لديك مهلة حتى",
        deadlineDate: "15 أكتوبر 2024",
        deadlineSuffix: "لتقديم هذه المستندات.",
        deadlineBadge: "إجراء مطلوب بسرعة",
        nextSteps: "عرض الإجراءات"
      },
      three: {
        browserTitle: "Simplifia",
        headerTitle: "Simplifia",
        replyTemplateTitle: "نموذج رد",
        dynamicContentTitle: "تبسيط المستند",
        replyTemplateBody: "السيدة، السيد،\n\nإشارة إلى رسالتكم المؤرخة في [التاريخ]، أؤكد أن المستندات المطلوبة قد تم تحميلها على مساحتي الشخصية.\n\nوأبقى رهن إشارتكم لأي معلومات إضافية.\n\nمع خالص التحية،\n[اسمك]",
        copyButton: "نسخ",
        copyFeedback: "تم نسخ النص إلى الحافظة.",
        helpTitle: "هل تحتاج إلى مساعدة حضورية؟",
        openUntil: "مفتوح حتى 17:00",
        directions: "الذهاب إلى هناك"
      }
    }
  };

  let currentLanguage = getInitialLanguage();
  let currentDevMode = getInitialDevMode();
  let languageListenersBound = false;

  function isSupportedLanguage(language) {
    return Object.prototype.hasOwnProperty.call(LANGUAGE_NAMES, language);
  }

  function parseBooleanParam(value) {
    return value === "1" || value === "true";
  }

  function getLanguageFromUrl() {
    try {
      const url = new URL(window.location.href);
      const language = url.searchParams.get(LANGUAGE_QUERY_PARAM);
      return isSupportedLanguage(language) ? language : null;
    } catch (_error) {
      return null;
    }
  }

  function getDevModeFromUrl() {
    try {
      const url = new URL(window.location.href);
      const devMode = url.searchParams.get(DEV_QUERY_PARAM);

      if (devMode === null) {
        return null;
      }

      return parseBooleanParam(devMode);
    } catch (_error) {
      return null;
    }
  }

  function getInitialLanguage() {
    return getLanguageFromUrl() ?? getStoredLanguage();
  }

  function getInitialDevMode() {
    return getDevModeFromUrl() ?? getStoredDevMode();
  }

  function buildAppUrl(path, options = {}) {
    const url = new URL(path, window.location.href);
    const language = options.language ?? currentLanguage;

    url.searchParams.set(LANGUAGE_QUERY_PARAM, language);
    url.searchParams.delete(DEV_QUERY_PARAM);

    return url.toString();
  }

  function syncStateInUrl() {
    try {
      const url = new URL(window.location.href);
      url.searchParams.set(LANGUAGE_QUERY_PARAM, currentLanguage);
      url.searchParams.delete(DEV_QUERY_PARAM);

      if (url.toString() !== window.location.href) {
        window.history.replaceState({}, "", url);
      }
    } catch (_error) {
      // Ignore URL sync errors in limited preview contexts.
    }
  }

  function getStoredLanguage() {
    try {
      const storedLanguage = window.localStorage.getItem(STORAGE_KEY);
      return isSupportedLanguage(storedLanguage)
        ? storedLanguage
        : DEFAULT_LANGUAGE;
    } catch (_error) {
      return DEFAULT_LANGUAGE;
    }
  }

  function setStoredLanguage(language) {
    try {
      window.localStorage.setItem(STORAGE_KEY, language);
    } catch (_error) {
      // Ignore storage errors in static previews.
    }
  }

  function getStoredDevMode() {
    try {
      return window.localStorage.getItem(DEV_MODE_KEY) === "1";
    } catch (_error) {
      return false;
    }
  }

  function setStoredDevMode(enabled) {
    try {
      window.localStorage.setItem(DEV_MODE_KEY, enabled ? "1" : "0");
    } catch (_error) {
      // Ignore storage errors in static previews.
    }
  }

  function readWindowState() {
    try {
      if (!window.name.startsWith(WINDOW_NAME_STATE_PREFIX)) {
        return {};
      }

      const serializedState = window.name.slice(WINDOW_NAME_STATE_PREFIX.length);
      const parsedState = JSON.parse(serializedState);

      return parsedState && typeof parsedState === "object" ? parsedState : {};
    } catch (_error) {
      return {};
    }
  }

  function writeWindowState(nextState) {
    try {
      if (!nextState || Object.keys(nextState).length === 0) {
        window.name = "";
        return;
      }

      window.name = `${WINDOW_NAME_STATE_PREFIX}${JSON.stringify(nextState)}`;
    } catch (_error) {
      // Ignore window.name persistence errors.
    }
  }

  function getTransientState(key) {
    try {
      const storedValue = window.sessionStorage.getItem(key);

      if (storedValue !== null) {
        return JSON.parse(storedValue);
      }
    } catch (_error) {
      // Ignore sessionStorage read errors.
    }

    const windowState = readWindowState();
    return Object.prototype.hasOwnProperty.call(windowState, key) ? windowState[key] : null;
  }

  function setTransientState(key, value) {
    const windowState = readWindowState();

    if (value === null || value === undefined) {
      delete windowState[key];
    } else {
      windowState[key] = value;
    }

    writeWindowState(windowState);

    try {
      if (value === null || value === undefined) {
        window.sessionStorage.removeItem(key);
      } else {
        window.sessionStorage.setItem(key, JSON.stringify(value));
      }
    } catch (_error) {
      // Ignore sessionStorage write errors.
    }
  }

  function getStoredAnalysisResult() {
    const result = getTransientState(ANALYSIS_RESULT_STORAGE_KEY);
    return result && typeof result === "object" ? result : null;
  }

  function setStoredAnalysisResult(result) {
    setTransientState(ANALYSIS_RESULT_STORAGE_KEY, result);
  }

  function clearStoredAnalysisResult() {
    setTransientState(ANALYSIS_RESULT_STORAGE_KEY, null);
  }

  function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();

      reader.addEventListener("load", () => {
        if (typeof reader.result !== "string") {
          reject(new Error(translate("index.photoResponseError")));
          return;
        }

        const separatorIndex = reader.result.indexOf(",");
        resolve(separatorIndex >= 0 ? reader.result.slice(separatorIndex + 1) : reader.result);
      });

      reader.addEventListener("error", () => {
        reject(new Error(translate("index.photoUploadError")));
      });

      reader.readAsDataURL(file);
    });
  }

  async function requestImageAnalysis(file) {
    const image_b64 = await readFileAsBase64(file);

    let response;

    try {
      response = await fetch(IMAGE_ANALYSIS_ENDPOINT, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ image_b64 })
      });
    } catch (_error) {
      throw new Error(translate("index.photoUploadError"));
    }

    if (!response.ok) {
      let errorMessage = `${translate("index.photoUploadError")} (${response.status})`;

      try {
        const errorPayload = await response.json();
        const responseMessage = errorPayload?.detail || errorPayload?.error || errorPayload?.answer;

        if (typeof responseMessage === "string" && responseMessage.trim()) {
          errorMessage = responseMessage;
        }
      } catch (_error) {
        // Ignore non-JSON error payloads and keep the default message.
      }

      throw new Error(errorMessage);
    }

    let payload;

    try {
      payload = await response.json();
    } catch (_error) {
      throw new Error(translate("index.photoResponseError"));
    }

    const normalizedPayload = payload && typeof payload === "object" ? payload : {};
    const answer = typeof normalizedPayload.answer === "string" ? normalizedPayload.answer.trim() : "";
    const responseType = typeof payload.type === "string" ? payload.type.toLowerCase() : "";
    const errorMessage = typeof payload.error === "string" ? payload.error.trim() : "";
    const primaryText = getStoredResultText(normalizedPayload, ["analysis", "answer", "summary", "simplification"]);

    if (errorMessage && responseType && responseType !== "success") {
      throw new Error(errorMessage);
    }

    if (!primaryText) {
      throw new Error(translate("index.photoResponseError"));
    }

    if (responseType && responseType !== "success") {
      throw new Error(answer || primaryText);
    }

    return {
      ...normalizedPayload,
      answer: answer || primaryText,
      type: typeof payload.type === "string" ? payload.type : "success"
    };
  }

  function getStoredResultText(result, keys) {
    if (!result || typeof result !== "object") {
      return "";
    }

    for (const key of keys) {
      const value = result[key];

      if (typeof value === "string" && value.trim()) {
        return value.trim();
      }
    }

    return "";
  }

  function getStoredResultDocumentTitle(result) {
    return getStoredResultText(result, ["document_title", "documentTitle", "title", "name"]);
  }

  function getPrimaryAnalysisText(result) {
    return getStoredResultText(result, ["analysis", "answer", "summary", "simplification"]);
  }

  function getSecondaryAnalysisText(result) {
    return getStoredResultText(result, ["simplification", "summary", "analysis", "answer"]);
  }

  function setTakePhotoButtonsPending(isPending) {
    document.querySelectorAll("[data-primary-action='take-photo']").forEach((button) => {
      const label = button.querySelector("[data-take-photo-label]");

      button.disabled = isPending;
      button.classList.toggle("opacity-60", isPending);
      button.classList.toggle("cursor-wait", isPending);

      if (label) {
        label.textContent = isPending ? translate("index.photoUploading") : translate("index.takePhoto");
      }
    });
  }

  async function handleSelectedPhoto(input) {
    if (!(input instanceof HTMLInputElement) || !input.files || input.files.length === 0) {
      return;
    }

    setTakePhotoButtonsPending(true);
    clearStoredAnalysisResult();

    try {
      const analysisResult = await requestImageAnalysis(input.files[0]);
      setStoredAnalysisResult(analysisResult);
      navigate("loader.html");
    } catch (error) {
      console.error("Image analysis failed:", error);
      window.alert(error instanceof Error ? error.message : translate("index.photoUploadError"));
      setTakePhotoButtonsPending(false);
    }
  }

  function hydrateAnalysisResultPage() {
    const analysisResult = getStoredAnalysisResult();
    const answerElement = document.querySelector("[data-analysis-answer]");
    const analysisText = getPrimaryAnalysisText(analysisResult);

    if (!analysisResult || !answerElement || !analysisText) {
      return;
    }

    const documentTitle = document.querySelector("[data-analysis-document-title]");
    const analysisSectionTitle = document.querySelector("[data-analysis-section-title]");
    const analysisIcon = document.querySelector("[data-analysis-section-icon]");
    const dynamicTitle = getStoredResultDocumentTitle(analysisResult);

    if (documentTitle) {
      documentTitle.textContent = dynamicTitle || translate("second.dynamicDocumentTitle");
    }

    if (analysisSectionTitle) {
      analysisSectionTitle.textContent = translate("second.analysisTitle");
    }

    if (analysisIcon) {
      analysisIcon.classList.remove("text-marianne-red", "icon-fill");
      analysisIcon.classList.add("text-navy-blue");
      analysisIcon.textContent = "auto_awesome";
    }

    answerElement.textContent = analysisText;

    document.querySelectorAll("[data-analysis-static-section]").forEach((section) => {
      section.classList.add("hidden");
    });
  }

  function hydrateFollowUpResultPage() {
    const analysisResult = getStoredAnalysisResult();
    const detailBody = document.querySelector("[data-result-detail-body]");
    const detailText = getSecondaryAnalysisText(analysisResult);

    if (!analysisResult || !detailBody || !detailText) {
      return;
    }

    const detailTitle = document.querySelector("[data-result-detail-title]");

    if (detailTitle) {
      detailTitle.textContent = translate("three.dynamicContentTitle");
    }

    detailBody.textContent = detailText;
  }

  function hydrateStoredResultPages() {
    hydrateAnalysisResultPage();
    hydrateFollowUpResultPage();
  }

  function getTranslationValue(language, key) {
    return key.split(".").reduce((value, part) => {
      if (value && Object.prototype.hasOwnProperty.call(value, part)) {
        return value[part];
      }
      return undefined;
    }, TRANSLATIONS[language]);
  }

  function translate(key, language = currentLanguage) {
    return (
      getTranslationValue(language, key) ??
      getTranslationValue(DEFAULT_LANGUAGE, key) ??
      key
    );
  }

  function updateTranslatedText(language) {
    document.documentElement.lang = language;
    document.documentElement.dir = RTL_LANGUAGES.has(language) ? "rtl" : "ltr";

    document.querySelectorAll("[data-i18n]").forEach((element) => {
      element.textContent = translate(element.dataset.i18n, language);
    });
  }

  function closeAllLanguageMenus() {
    document.querySelectorAll("[data-language-selector]").forEach((selector) => {
      const menu = selector.querySelector("[data-language-menu]");
      const trigger = selector.querySelector("[data-language-trigger]");

      if (menu) {
        menu.classList.add("hidden");
      }

      if (trigger) {
        trigger.setAttribute("aria-expanded", "false");
      }
    });
  }

  function updateLanguageSelectors(language) {
    document.querySelectorAll("[data-language-current-label]").forEach((label) => {
      label.textContent = LANGUAGE_NAMES[language];
    });

    document.querySelectorAll("[data-language-option]").forEach((option) => {
      const isActive = option.dataset.languageOption === language;
      const badge = option.querySelector("[data-language-badge]");
      const check = option.querySelector("[data-language-check]");

      option.classList.toggle("bg-surface-container-low", isActive);
      option.classList.toggle("text-navy-blue", isActive);
      option.setAttribute("aria-pressed", isActive ? "true" : "false");

      if (badge) {
        badge.classList.toggle("bg-transparent", !isActive);
        badge.classList.toggle("border-outline", !isActive);
        badge.classList.toggle("text-on-surface-variant", !isActive);
        badge.classList.toggle("bg-navy-blue", isActive);
        badge.classList.toggle("border-navy-blue", isActive);
        badge.classList.toggle("text-white", isActive);
      }

      if (check) {
        check.classList.toggle("invisible", !isActive);
      }
    });
  }

  function updateAppLinks() {
    document.querySelectorAll("[data-app-link]").forEach((element) => {
      const targetPath = element.dataset.appLink;
      const href = buildAppUrl(targetPath);

      if (element instanceof HTMLAnchorElement) {
        element.href = href;
      } else {
        element.dataset.appHref = href;
      }
    });
  }

  function updateDevModeToggles() {
    document.querySelectorAll("[data-dev-mode-toggle]").forEach((button) => {
      button.setAttribute("aria-pressed", currentDevMode ? "true" : "false");
      button.style.backgroundColor = currentDevMode ? "#000091" : "#fcf9f8";
      button.style.borderColor = currentDevMode ? "#000091" : "#c6c5d6";
      button.style.color = currentDevMode ? "#ffffff" : "#000091";
      button.style.boxShadow = currentDevMode ? "0 1px 2px rgba(0, 0, 0, 0.08)" : "none";
    });
  }

  function setLanguage(language) {
    if (!isSupportedLanguage(language)) {
      return;
    }

    currentLanguage = language;
    setStoredLanguage(language);
    syncStateInUrl();
    updateTranslatedText(language);
    hydrateStoredResultPages();
    updateLanguageSelectors(language);
    updateAppLinks();
    closeAllLanguageMenus();
    document.dispatchEvent(
      new CustomEvent("app:languagechange", {
        detail: { language }
      })
    );
  }

  function setDevMode(enabled) {
    currentDevMode = Boolean(enabled);
    setStoredDevMode(currentDevMode);
    syncStateInUrl();
    updateDevModeToggles();
    updateAppLinks();
    document.dispatchEvent(
      new CustomEvent("app:devmodechange", {
        detail: { devMode: currentDevMode }
      })
    );
  }

  function navigate(path, options = {}) {
    window.location.href = buildAppUrl(path, options);
  }

  function bindLanguageSelectors() {
    if (!languageListenersBound) {
      document.addEventListener("click", (event) => {
        if (!(event.target instanceof Element) || !event.target.closest("[data-language-selector]")) {
          closeAllLanguageMenus();
        }
      });

      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          closeAllLanguageMenus();
        }
      });

      languageListenersBound = true;
    }

    document.querySelectorAll("[data-language-selector]").forEach((selector) => {
      const trigger = selector.querySelector("[data-language-trigger]");
      const menu = selector.querySelector("[data-language-menu]");

      if (!trigger || !menu || trigger.dataset.bound === "true") {
        return;
      }

      trigger.dataset.bound = "true";

      trigger.addEventListener("click", (event) => {
        event.stopPropagation();
        const shouldOpen = menu.classList.contains("hidden");
        closeAllLanguageMenus();

        if (shouldOpen) {
          menu.classList.remove("hidden");
          trigger.setAttribute("aria-expanded", "true");
        }
      });

      menu.querySelectorAll("[data-language-option]").forEach((option) => {
        option.addEventListener("click", () => {
          setLanguage(option.dataset.languageOption);
        });
      });
    });
  }

  function bindDevModeToggles() {
    document.querySelectorAll("[data-dev-mode-toggle]").forEach((button) => {
      if (button.dataset.devModeBound === "true") {
        return;
      }

      button.dataset.devModeBound = "true";
      button.addEventListener("click", () => {
        setDevMode(!currentDevMode);
      });
    });
  }

  function bindAppActions() {
    document.querySelectorAll("[data-app-link]").forEach((element) => {
      if (element instanceof HTMLAnchorElement || element.dataset.appLinkBound === "true") {
        return;
      }

      element.dataset.appLinkBound = "true";
      element.addEventListener("click", () => {
        navigate(element.dataset.appLink);
      });
    });

    document.querySelectorAll("[data-primary-action='take-photo']").forEach((button) => {
      if (button.dataset.primaryActionBound === "true") {
        return;
      }

      button.dataset.primaryActionBound = "true";
      button.addEventListener("click", () => {
        const fileInput = document.querySelector("[data-image-file-input]");

        if (fileInput instanceof HTMLInputElement) {
          fileInput.value = "";
          fileInput.click();
          return;
        }

        clearStoredAnalysisResult();
        navigate("loader.html");
      });
    });

    document.querySelectorAll("[data-primary-action='paste-text']").forEach((button) => {
      if (button.dataset.primaryActionBound === "true") {
        return;
      }

      button.dataset.primaryActionBound = "true";
      button.addEventListener("click", () => {
        clearStoredAnalysisResult();
        navigate("loader.html");
      });
    });

    document.querySelectorAll("[data-image-file-input]").forEach((input) => {
      if (input.dataset.devFileBound === "true") {
        return;
      }

      input.dataset.devFileBound = "true";
      input.addEventListener("change", async () => {
        await handleSelectedPhoto(input);
      });
    });
  }

  function initialize() {
    currentDevMode = false;
    setStoredDevMode(false);
    syncStateInUrl();
    updateTranslatedText(currentLanguage);
    hydrateStoredResultPages();
    bindLanguageSelectors();
    bindDevModeToggles();
    bindAppActions();
    updateLanguageSelectors(currentLanguage);
    updateAppLinks();
    updateDevModeToggles();
  }

  window.GovAppI18n = {
    getLanguage: () => currentLanguage,
    setLanguage,
    t: translate,
    urlFor: buildAppUrl,
    navigate,
    isDevMode: () => currentDevMode,
    setDevMode,
    toggleDevMode: () => setDevMode(!currentDevMode),
    getLatestAnalysisResult: getStoredAnalysisResult,
    clearLatestAnalysisResult: clearStoredAnalysisResult
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  } else {
    initialize();
  }
})();