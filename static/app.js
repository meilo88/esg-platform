document.addEventListener("DOMContentLoaded", () => {
  let selectedFile = null;
  let currentAnalysis = null;
  let currentAuditDimFilter = "all";
  let trendChartInstance = null;
  let currentCompanyCode = "002241";
  let currentReportDetailId = null;
  let currentReportCompanyCode = null;
  let cachedRankingsData = [];

  function escapeHtml(val) {
    if (val === null || val === undefined) return "";
    return String(val)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatNumber(val) {
    if (val === null || val === undefined || val === "") return "--";
    const num = Number(val);
    if (Number.isNaN(num)) return escapeHtml(val);
    return num.toLocaleString("zh-CN", { maximumFractionDigits: 4 });
  }

  // ==================== 轻量级非阻塞 Toast 通知组件 ====================
  function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const palette = {
      success: {
        border: "border-emerald-200",
        icon: "ph-check-circle text-emerald-600",
        bg: "bg-white"
      },
      error: {
        border: "border-rose-200",
        icon: "ph-warning-circle text-rose-600",
        bg: "bg-white"
      },
      warning: {
        border: "border-amber-200",
        icon: "ph-warning text-amber-600",
        bg: "bg-white"
      },
      info: {
        border: "border-slate-200",
        icon: "ph-info text-blue-600",
        bg: "bg-white"
      }
    };
    const style = palette[type] || palette.info;

    const item = document.createElement("div");
    item.className = `pointer-events-auto ${style.bg} border ${style.border} rounded-xl shadow-lg px-4 py-3 flex items-start space-x-2.5 text-xs text-slate-800 toast-enter`;
    item.innerHTML = `
      <i class="ph ${style.icon} text-base mt-0.5 flex-shrink-0"></i>
      <div class="flex-1 leading-relaxed whitespace-pre-line font-medium">${escapeHtml(message)}</div>
      <button class="text-slate-400 hover:text-slate-600 ml-1 cursor-pointer leading-none text-sm">&times;</button>
    `;

    const dismiss = () => {
      if (item.dataset.closing) return;
      item.dataset.closing = "1";
      item.classList.remove("toast-enter");
      item.classList.add("toast-leave");
      setTimeout(() => item.remove(), 180);
    };

    item.querySelector("button").addEventListener("click", dismiss);
    container.appendChild(item);
    setTimeout(dismiss, 3800);
  }

  // ==================== 0. 管理员模式鉴权与安全会话体系 ====================
  let isAdmin = false;
  let serverSettingsCache = null;

  const btnAdminLogin = document.getElementById("btn-admin-login");
  const adminLoggedBar = document.getElementById("admin-logged-bar");
  const btnAdminLogout = document.getElementById("btn-admin-logout");
  const modalAdminLogin = document.getElementById("modal-admin-login");
  const adminLoginClose = document.getElementById("admin-login-close");
  const adminLoginBtnCancel = document.getElementById("admin-login-btn-cancel");
  const adminPasswordInput = document.getElementById("admin-password-input");
  const adminLoginBtnConfirm = document.getElementById("admin-login-btn-confirm");
  const adminLoginError = document.getElementById("admin-login-error");
  const adminLoginErrorText = document.getElementById("admin-login-error-text");
  const userPrivateNotice = document.getElementById("user-private-notice");
  const adminPublishContainer = document.getElementById("admin-publish-container");
  const btnAdminPublishReport = document.getElementById("btn-admin-publish-report");
  const adminPublishStatusTitle = document.getElementById("admin-publish-status-title");
  const adminPublishCodeInput = document.getElementById("admin-publish-code");
  const adminPublishIndustrySelect = document.getElementById("admin-publish-industry");
  const adminHeaderBtnSettings = document.getElementById("admin-header-btn-settings");
  const adminHeaderBtnImport = document.getElementById("admin-header-btn-import");

  function refreshExtractionBanners() {
    if (!currentAnalysis) {
      if (userPrivateNotice) userPrivateNotice.classList.add("hidden");
      if (adminPublishContainer) adminPublishContainer.classList.add("hidden");
      return;
    }

    if (isAdmin) {
      if (userPrivateNotice) userPrivateNotice.classList.add("hidden");
      if (adminPublishContainer) adminPublishContainer.classList.remove("hidden");

      const sum = currentAnalysis.summary || {};
      if (adminPublishCodeInput && !adminPublishCodeInput.dataset.reportBound) {
        adminPublishCodeInput.value = sum.company_code || "";
        adminPublishCodeInput.dataset.reportBound = "1";
      }
      if (adminPublishIndustrySelect && !adminPublishIndustrySelect.dataset.reportBound) {
        adminPublishIndustrySelect.value = sum.industry_l1 || "电子";
        adminPublishIndustrySelect.dataset.reportBound = "1";
      }

      if (currentAnalysis.is_published) {
        if (adminPublishStatusTitle) {
          adminPublishStatusTitle.textContent = "该报告已收录入库，对前台访客公开";
          adminPublishStatusTitle.className = "text-xs font-bold text-emerald-900";
        }
        if (adminPublishCodeInput) adminPublishCodeInput.disabled = true;
        if (adminPublishIndustrySelect) adminPublishIndustrySelect.disabled = true;
        if (btnAdminPublishReport) {
          btnAdminPublishReport.disabled = true;
          btnAdminPublishReport.className = "bg-slate-200 text-slate-500 font-semibold text-xs py-1.5 px-3.5 rounded-lg transition flex items-center space-x-1.5 whitespace-nowrap cursor-not-allowed";
          btnAdminPublishReport.innerHTML = '<i class="ph ph-check-circle text-sm"></i><span>已收录入库</span>';
        }
      } else {
        if (adminPublishStatusTitle) {
          adminPublishStatusTitle.textContent = "该报告暂未收录入库";
          adminPublishStatusTitle.className = "text-xs font-bold text-amber-900";
        }
        if (adminPublishCodeInput) adminPublishCodeInput.disabled = false;
        if (adminPublishIndustrySelect) adminPublishIndustrySelect.disabled = false;
        if (btnAdminPublishReport) {
          btnAdminPublishReport.disabled = false;
          btnAdminPublishReport.className = "bg-amber-600 hover:bg-amber-700 text-white font-semibold text-xs py-1.5 px-3.5 rounded-lg shadow-xs transition flex items-center space-x-1.5 whitespace-nowrap cursor-pointer";
          btnAdminPublishReport.innerHTML = '<i class="ph ph-cloud-arrow-up text-sm"></i><span>确认收录入库</span>';
        }
      }
    } else {
      if (userPrivateNotice) userPrivateNotice.classList.remove("hidden");
      if (adminPublishContainer) adminPublishContainer.classList.add("hidden");
    }
  }

  function updateSettingsModalFields(cfg) {
    if (!cfg) return;
    serverSettingsCache = cfg;
    const cfgProvider = document.getElementById("cfg-provider");
    const cfgModel = document.getElementById("cfg-model");
    const cfgBaseUrl = document.getElementById("cfg-base-url");
    const divBaseUrl = document.getElementById("div-base-url");
    const cfgKeyStatus = document.getElementById("cfg-key-status");
    const currentModelTag = document.getElementById("current-model-tag");

    const provider = cfg.provider || "gemini";
    const hasActiveKey = provider === "gemini" ? !!cfg.has_gemini_key : !!cfg.has_openai_key;

    if (currentModelTag) {
      if (hasActiveKey) {
        currentModelTag.textContent = provider === "gemini" ? "Gemini 已启用" : "大模型已启用";
      } else {
        currentModelTag.textContent = "模型配置";
      }
    }

    if (cfgProvider) cfgProvider.value = provider;
    if (divBaseUrl) divBaseUrl.classList.toggle("hidden", provider !== "openai");
    if (cfgModel) {
      cfgModel.value = provider === "gemini" ? (cfg.gemini_model || "") : (cfg.openai_model || "");
    }
    if (cfgBaseUrl && cfg.openai_base_url) {
      cfgBaseUrl.value = cfg.openai_base_url;
    }
    if (cfgKeyStatus) {
      if (hasActiveKey) {
        cfgKeyStatus.textContent = "● 已配置密钥（留空保留现有密钥）";
        cfgKeyStatus.className = "text-[11px] font-semibold text-emerald-600";
      } else {
        cfgKeyStatus.textContent = "○ 未配置密钥（当前使用离线解析）";
        cfgKeyStatus.className = "text-[11px] font-medium text-amber-600";
      }
    }
  }

  async function syncAdminSettingsStatus() {
    if (!isAdmin) return;
    const token = sessionStorage.getItem("esg_admin_token") || "";
    if (!token) return;
    try {
      const resp = await fetch("/api/settings", {
        headers: { "X-Admin-Token": token }
      });
      if (resp.ok) {
        const cfg = await resp.json();
        updateSettingsModalFields(cfg);
      }
    } catch (e) {}
  }

  function updateAdminUI() {
    if (isAdmin) {
      if (btnAdminLogin) btnAdminLogin.classList.add("hidden");
      if (adminLoggedBar) {
        adminLoggedBar.classList.remove("hidden");
        adminLoggedBar.classList.add("flex");
      }
      const detailBtnExportWorkpaper = document.getElementById("detail-btn-export-workpaper");
      if (detailBtnExportWorkpaper) detailBtnExportWorkpaper.classList.remove("hidden");
    } else {
      if (btnAdminLogin) btnAdminLogin.classList.remove("hidden");
      if (adminLoggedBar) {
        adminLoggedBar.classList.add("hidden");
        adminLoggedBar.classList.remove("flex");
      }
      const detailBtnExportWorkpaper = document.getElementById("detail-btn-export-workpaper");
      if (detailBtnExportWorkpaper) detailBtnExportWorkpaper.classList.add("hidden");
    }
    refreshExtractionBanners();
  }

  const savedAdminToken = sessionStorage.getItem("esg_admin_token");
  if (savedAdminToken) {
    fetch("/api/admin/verify", {
      headers: { "X-Admin-Token": savedAdminToken }
    })
      .then(r => r.json())
      .then(d => {
        isAdmin = !!d.is_admin;
        if (!isAdmin) sessionStorage.removeItem("esg_admin_token");
        updateAdminUI();
        if (isAdmin) syncAdminSettingsStatus();
      })
      .catch(() => {
        isAdmin = false;
        sessionStorage.removeItem("esg_admin_token");
        updateAdminUI();
      });
  }

  function openAdminLoginModal() {
    if (adminLoginError) adminLoginError.classList.add("hidden");
    const modal = document.getElementById("modal-admin-login");
    if (modal) {
      modal.classList.remove("hidden");
      modal.style.display = "flex";
    }
    if (adminPasswordInput) {
      adminPasswordInput.value = "";
      setTimeout(() => adminPasswordInput.focus(), 60);
    }
  }

  function closeAdminLoginModal() {
    if (adminLoginError) adminLoginError.classList.add("hidden");
    const modal = document.getElementById("modal-admin-login");
    if (modal) {
      modal.classList.add("hidden");
      modal.style.display = "none";
    }
  }

  async function doAdminLogin() {
    const pwd = (adminPasswordInput ? adminPasswordInput.value : "").trim();
    if (!pwd) {
      if (adminLoginErrorText) adminLoginErrorText.textContent = "请输入管理员密码";
      if (adminLoginError) adminLoginError.classList.remove("hidden");
      if (adminPasswordInput) adminPasswordInput.focus();
      return;
    }

    if (adminLoginBtnConfirm) {
      adminLoginBtnConfirm.disabled = true;
      adminLoginBtnConfirm.innerHTML = '<i class="ph ph-spinner animate-spin mr-1"></i>验证中...';
    }

    try {
      const resp = await fetch("/api/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: pwd })
      });
      const data = await resp.json();

      if (resp.ok && data.token) {
        sessionStorage.setItem("esg_admin_token", data.token);
        isAdmin = true;
        updateAdminUI();
        syncAdminSettingsStatus();
        closeAdminLoginModal();
        if (adminPasswordInput) adminPasswordInput.value = "";
        loadReportsView();
        loadRankingsView();
        showToast("已进入管理员模式", "success");
      } else {
        isAdmin = false;
        sessionStorage.removeItem("esg_admin_token");
        if (adminLoginErrorText) adminLoginErrorText.textContent = data.detail || "管理密码错误";
        if (adminLoginError) adminLoginError.classList.remove("hidden");
        if (adminPasswordInput) {
          adminPasswordInput.value = "";
          adminPasswordInput.focus();
        }
      }
    } catch (e) {
      if (adminLoginErrorText) adminLoginErrorText.textContent = "请求异常: " + e.message;
      if (adminLoginError) adminLoginError.classList.remove("hidden");
    } finally {
      if (adminLoginBtnConfirm) {
        adminLoginBtnConfirm.disabled = false;
        adminLoginBtnConfirm.textContent = "登录";
      }
    }
  }

  async function doAdminLogout() {
    const token = sessionStorage.getItem("esg_admin_token");
    if (token) {
      try {
        await fetch("/api/admin/logout", {
          method: "POST",
          headers: { "X-Admin-Token": token }
        });
      } catch (e) {}
    }
    isAdmin = false;
    serverSettingsCache = null;
    sessionStorage.removeItem("esg_admin_token");
    updateAdminUI();
    loadReportsView();
    loadRankingsView();
    showToast("已退出管理员模式", "info");
  }

  window.openAdminLoginModal = openAdminLoginModal;
  window.closeAdminLoginModal = closeAdminLoginModal;
  window.doAdminLogin = doAdminLogin;
  window.doAdminLogout = doAdminLogout;

  if (btnAdminLogin) btnAdminLogin.addEventListener("click", openAdminLoginModal);
  if (adminLoginClose) adminLoginClose.addEventListener("click", closeAdminLoginModal);
  if (adminLoginBtnCancel) adminLoginBtnCancel.addEventListener("click", closeAdminLoginModal);
  if (btnAdminLogout) btnAdminLogout.addEventListener("click", doAdminLogout);
  if (adminLoginBtnConfirm) adminLoginBtnConfirm.addEventListener("click", doAdminLogin);
  if (adminPasswordInput) {
    adminPasswordInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") doAdminLogin();
    });
  }
  if (adminHeaderBtnSettings) {
    adminHeaderBtnSettings.addEventListener("click", () => {
      const cfgApiKey = document.getElementById("cfg-api-key");
      if (cfgApiKey) cfgApiKey.value = "";
      syncAdminSettingsStatus();
      const modalSettings = document.getElementById("modal-settings");
      if (modalSettings) modalSettings.classList.remove("hidden");
    });
  }
  if (adminHeaderBtnImport) {
    adminHeaderBtnImport.addEventListener("click", () => {
      const annotationFileInput = document.getElementById("annotation-file-input");
      if (annotationFileInput) annotationFileInput.click();
    });
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("#btn-admin-login");
    if (btn) {
      e.preventDefault();
      openAdminLoginModal();
    }
  });

  // ==================== 深色/浅色模式切换 ====================
  const btnThemeToggle = document.getElementById("btn-theme-toggle");
  const themeToggleIcon = document.getElementById("theme-toggle-icon");

  function updateThemeUI(isDark) {
    if (themeToggleIcon) {
      themeToggleIcon.className = isDark ? "ph ph-sun text-base text-amber-300" : "ph ph-moon text-base text-slate-300";
    }
  }

  // 初始化主题图标
  updateThemeUI(document.documentElement.classList.contains("dark"));

  if (btnThemeToggle) {
    btnThemeToggle.addEventListener("click", () => {
      const isDark = document.documentElement.classList.toggle("dark");
      localStorage.setItem("esg_theme", isDark ? "dark" : "light");
      updateThemeUI(isDark);
      if (currentCompanyCode && trendIndicatorSelect) {
        loadCompanyTrend(currentCompanyCode, trendIndicatorSelect.value);
      }
    });
  }

  updateAdminUI();

  // ==================== 1. 视图切换与跨板块联动 ====================
  const navTabs = document.querySelectorAll(".nav-tab");
  const viewPanels = document.querySelectorAll(".view-panel");

  function switchView(targetViewId) {
    viewPanels.forEach(p => p.classList.add("hidden"));
    navTabs.forEach(t => {
      t.classList.remove("active");
      t.classList.add("text-slate-300");
    });

    const targetPanel = document.getElementById(targetViewId);
    if (targetPanel) targetPanel.classList.remove("hidden");

    const navTarget = targetViewId === "view-report-detail" ? "view-reports" : targetViewId;
    document.querySelectorAll(`.nav-tab[data-view="${navTarget}"]`).forEach(activeTab => {
      activeTab.classList.add("active");
      activeTab.classList.remove("text-slate-300");
    });

    if (targetViewId === "view-companies") {
      loadCompaniesView();
      requestAnimationFrame(() => {
        if (trendChartInstance) trendChartInstance.resize();
      });
    }
    if (targetViewId === "view-reports") loadReportsView();
    if (targetViewId === "view-rankings") loadRankingsView();
    if (targetViewId === "view-home") loadStats();
    if (targetViewId === "view-audit") loadSamples();

    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function navigateToCompany(code, indicatorCode = null) {
    if (!code) return;
    currentCompanyCode = code;
    if (companySearchInput) {
      companySearchInput.value = "";
      if (companySearchClear) companySearchClear.classList.add("hidden");
    }
    if (companyIndustryFilter) {
      companyIndustryFilter.value = "全部";
    }
    if (indicatorCode && trendIndicatorSelect) {
      const hasOption = Array.from(trendIndicatorSelect.options).some(o => o.value === indicatorCode);
      if (hasOption) trendIndicatorSelect.value = indicatorCode;
    }
    switchView("view-companies");
  }

  function navigateToCompanyReports(keyword) {
    if (!keyword) return;
    currentReportYearFilter = "";
    document.querySelectorAll(".rep-filter-year").forEach(b => {
      const isAll = b.getAttribute("data-year") === "";
      b.classList.toggle("active", isAll);
      b.classList.toggle("bg-white", isAll);
      b.classList.toggle("text-slate-900", isAll);
      b.classList.toggle("shadow-xs", isAll);
      b.classList.toggle("font-semibold", isAll);
      b.classList.toggle("text-slate-600", !isAll);
      b.classList.toggle("font-medium", !isAll);
    });
    if (reportsStatusFilter) reportsStatusFilter.value = "全部";
    if (reportsSearchInput) {
      reportsSearchInput.value = keyword;
      if (reportsSearchClear) reportsSearchClear.classList.remove("hidden");
    }
    switchView("view-reports");
  }

  navTabs.forEach(tab => {
    tab.addEventListener("click", () => switchView(tab.getAttribute("data-view")));
  });

  const navBrandHome = document.getElementById("nav-brand-home");
  if (navBrandHome) {
    navBrandHome.addEventListener("click", () => switchView("view-home"));
  }

  document.querySelectorAll(".btn-home-jump").forEach(card => {
    card.addEventListener("click", () => {
      const target = card.getAttribute("data-target");
      if (target) switchView(target);
    });
  });

  const btnBackToReports = document.getElementById("btn-back-to-reports");
  if (btnBackToReports) {
    btnBackToReports.addEventListener("click", () => switchView("view-reports"));
  }

  // ==================== 2. 公司库 (Companies) ====================
  const companyCardsList = document.getElementById("company-cards-list");
  const companySearchInput = document.getElementById("company-search-input");
  const companySearchClear = document.getElementById("company-search-clear");
  const companyIndustryFilter = document.getElementById("company-industry-filter");
  const trendIndicatorSelect = document.getElementById("trend-indicator-select");
  const btnCompViewReports = document.getElementById("btn-comp-view-reports");

  function loadCompaniesView() {
    const kw = companySearchInput ? companySearchInput.value.trim() : "";
    const ind = companyIndustryFilter ? companyIndustryFilter.value : "全部";
    let url = `/api/companies?`;
    if (kw) url += `keyword=${encodeURIComponent(kw)}&`;
    if (ind && ind !== "全部") url += `industry=${encodeURIComponent(ind)}&`;

    fetch(url)
      .then(r => r.json())
      .then(data => {
        const list = data.companies || [];
        const badge = document.getElementById("company-count-badge");
        if (badge) badge.textContent = `${list.length} 家`;

        if (list.length > 0) {
          const matched = list.find(c => c.code === currentCompanyCode) || list[0];
          currentCompanyCode = matched.code;
          renderCompanyCards(list);
          selectCompany(matched.code);
        } else {
          renderCompanyCards([]);
        }
      });
  }

  if (companySearchInput) {
    companySearchInput.addEventListener("input", () => {
      if (companySearchClear) {
        companySearchClear.classList.toggle("hidden", !companySearchInput.value);
      }
      loadCompaniesView();
    });
  }

  if (companySearchClear) {
    companySearchClear.addEventListener("click", () => {
      companySearchInput.value = "";
      companySearchClear.classList.add("hidden");
      loadCompaniesView();
    });
  }

  if (companyIndustryFilter) {
    companyIndustryFilter.addEventListener("change", () => loadCompaniesView());
  }

  if (trendIndicatorSelect) {
    trendIndicatorSelect.addEventListener("change", () => {
      loadCompanyTrend(currentCompanyCode, trendIndicatorSelect.value);
    });
  }

  if (btnCompViewReports) {
    btnCompViewReports.addEventListener("click", () => {
      const compName = document.getElementById("detail-comp-name")?.textContent;
      if (compName && compName !== "--" && compName !== "暂无收录企业") {
        navigateToCompanyReports(compName);
      }
    });
  }

  function renderCompanyCards(companies) {
    companyCardsList.innerHTML = "";
    const selectedInd = companyIndustryFilter ? companyIndustryFilter.value : "全部";

    if (companies.length === 0) {
      const isAll = !selectedInd || selectedInd === "全部";
      const displayInd = isAll ? "当前筛选条件" : `「${escapeHtml(selectedInd)}」行业`;
      companyCardsList.innerHTML = `
        <div class="p-6 text-center bg-white rounded-2xl border border-dashed border-slate-200 space-y-3">
          <div class="w-10 h-10 rounded-full bg-slate-100 text-slate-500 mx-auto flex items-center justify-center text-lg">
            <i class="ph ph-buildings"></i>
          </div>
          <div>
            <div class="font-bold text-slate-800 text-xs">${displayInd}暂无企业记录</div>
            <p class="text-[11px] text-slate-400 mt-1 leading-relaxed">
              可通过「智能抽取」上传报告解析指标。
            </p>
          </div>
          <button class="btn-empty-jump-audit px-3.5 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs transition inline-flex items-center space-x-1 cursor-pointer">
            <i class="ph ph-sparkle"></i>
            <span>前往智能抽取</span>
          </button>
        </div>
      `;
      const btnEmptyJump = companyCardsList.querySelector(".btn-empty-jump-audit");
      if (btnEmptyJump) {
        btnEmptyJump.onclick = () => switchView("view-audit");
      }
      resetCompanyDetailEmpty(displayInd);
      return;
    }

    companies.forEach(c => {
      const isSelected = c.code === currentCompanyCode;
      const years = Array.isArray(c.available_years) && c.available_years.length > 0
        ? (c.available_years.length > 1 ? `${c.available_years[0]}–${c.available_years[c.available_years.length - 1]}` : `${c.available_years[0]}`)
        : "";
      const repInfo = years ? `${years} · ${Number(c.reports_count || 0)} 份报告` : `${Number(c.reports_count || 0)} 份报告`;

      const div = document.createElement("div");
      div.dataset.code = c.code;
      div.className = `company-card-item p-3.5 rounded-xl border cursor-pointer transition ${
        isSelected
          ? "border-blue-500 bg-blue-50/40 shadow-xs ring-1 ring-blue-500/20"
          : "border-slate-200/90 bg-white hover:border-slate-300"
      }`;
      div.innerHTML = `
        <div class="flex items-center justify-between gap-2">
          <span class="font-bold text-sm text-slate-900 truncate">${escapeHtml(c.name)}</span>
          <span class="font-mono text-[11px] px-1.5 py-0.5 rounded-md ${isSelected ? "bg-blue-100/80 text-blue-700" : "bg-slate-100 text-slate-600"} font-semibold flex-shrink-0">${escapeHtml(c.code)}</span>
        </div>
        <div class="text-[11px] text-slate-500 mt-2 flex items-center justify-between">
          <span class="text-slate-500 truncate">${escapeHtml(c.industry)}</span>
          <span class="${isSelected ? "text-blue-600" : "text-slate-400"} font-mono flex-shrink-0">${escapeHtml(repInfo)}</span>
        </div>
      `;
      div.addEventListener("click", () => selectCompany(c.code));
      companyCardsList.appendChild(div);
    });
  }

  function resetCompanyDetailEmpty(displayInd) {
    document.getElementById("detail-comp-name").textContent = "暂无收录企业";
    document.getElementById("detail-comp-code").textContent = "--";
    document.getElementById("detail-comp-industry").textContent = displayInd.replace(/<[^>]+>/g, "");
    document.getElementById("detail-comp-exchange").textContent = "--";
    document.getElementById("detail-comp-reports-count").textContent = "0 份报告";
    if (btnCompViewReports) btnCompViewReports.classList.add("hidden");
    if (trendChartInstance) trendChartInstance.clear();
    const container = document.getElementById("company-kpi-accordions");
    if (container) {
      container.innerHTML = `<div class="p-8 text-center text-slate-400 text-xs bg-slate-50/70 rounded-xl border border-dashed border-slate-200">暂无数据，可前往「智能抽取」上传 PDF 报告提取指标。</div>`;
    }
  }

  function selectCompany(code) {
    currentCompanyCode = code;
    if (btnCompViewReports) btnCompViewReports.classList.remove("hidden");
    document.querySelectorAll(".company-card-item").forEach(card => {
      const active = card.dataset.code === code;
      card.className = `company-card-item p-3.5 rounded-xl border cursor-pointer transition ${
        active
          ? "border-blue-500 bg-blue-50/40 shadow-xs ring-1 ring-blue-500/20"
          : "border-slate-200/90 bg-white hover:border-slate-300"
      }`;
    });
    loadCompanyTrend(code, trendIndicatorSelect.value);
  }

  function loadCompanyTrend(code, indicatorCode) {
    fetch(`/api/companies/${encodeURIComponent(code)}?indicator=${encodeURIComponent(indicatorCode)}`)
      .then(r => r.json())
      .then(d => {
        const comp = d.company;
        document.getElementById("detail-comp-name").textContent = comp.name;
        document.getElementById("detail-comp-code").textContent = comp.code;
        document.getElementById("detail-comp-industry").textContent = comp.industry;
        document.getElementById("detail-comp-exchange").textContent = comp.exchange;
        document.getElementById("detail-comp-reports-count").textContent = `${d.reports_count || 1} 份报告`;

        const latestYearTag = document.getElementById("company-latest-year-tag");
        if (latestYearTag && d.latest_kpis && d.latest_kpis.length > 0 && d.latest_kpis[0].year) {
          latestYearTag.textContent = `${d.latest_kpis[0].year}年度最新披露`;
        }

        renderTrendChart(d.trend_data || [], comp.name, indicatorCode, d.latest_kpis || []);
        renderCompanyAccordions(d.latest_kpis || [], indicatorCode);
      });
  }

  function renderTrendChart(trendData, compName, indicatorCode, latestKpis) {
    const chartDom = document.getElementById("echarts-trend-chart");
    if (!chartDom) return;
    if (!trendChartInstance) {
      trendChartInstance = echarts.init(chartDom);
      window.addEventListener("resize", () => trendChartInstance && trendChartInstance.resize());
    }

    let indLabel = indicatorCode;
    for (const opt of trendIndicatorSelect.options) {
      if (opt.value === indicatorCode) {
        indLabel = opt.text.replace(/\s*\([^)]*\)\s*$/, "");
        break;
      }
    }

    const matchedMeta = (latestKpis || []).find(k => k.indicator_code === indicatorCode);
    const stdUnit = matchedMeta?.std_unit || (trendData[0] && trendData[0].std_unit) || "";

    const titleEl = document.getElementById("trend-chart-title");
    const unitEl = document.getElementById("trend-chart-unit");
    if (titleEl) titleEl.textContent = indLabel;
    if (unitEl) {
      unitEl.textContent = stdUnit === "类别字段" ? "定性指标" : (stdUnit ? `单位: ${stdUnit}` : "--");
    }

    const years = [2022, 2023, 2024, 2025];
    const dataMap = {};
    trendData.forEach(item => {
      dataMap[item.year] = item;
    });

    const isQualitative = indicatorCode === "Q30" || stdUnit === "类别字段";
    const seriesData = years.map(y => {
      const item = dataMap[y];
      if (!item || item.std_value === null || item.std_value === undefined || isQualitative) {
        return { value: null };
      }
      return {
        value: item.std_value,
        itemStyle: { color: "#2563EB" },
        rawInfo: item
      };
    });

    const hasNumericPoint = seriesData.some(pt => pt.value !== null && pt.value !== undefined);

    let graphicOverlay = [];
    if (!hasNumericPoint) {
      const emptyMsg = isQualitative
        ? `定性披露项：${matchedMeta?.conv_note || matchedMeta?.raw_unit || "请查看下方指标明细"}`
        : "已收录报告暂未披露该项定量数值";
      graphicOverlay = [
        {
          type: "text",
          left: "center",
          top: "middle",
          style: {
            text: emptyMsg,
            fill: "#94A3B8",
            fontSize: 12,
            fontWeight: 500
          }
        }
      ];
    }

    const isDark = document.documentElement.classList.contains("dark");
    const option = {
      graphic: graphicOverlay,
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(15, 23, 42, 0.94)",
        borderWidth: 0,
        padding: [10, 12],
        textStyle: { color: "#F8FAFC", fontSize: 12 },
        formatter: (params) => {
          const p = params[0];
          if (!p || p.value === null || p.value === undefined) {
            return `<div style="font-size:11px;color:#CBD5E1;"><b>${escapeHtml(p?.name || "")}</b> · 暂无定量数据</div>`;
          }
          const raw = p.data.rawInfo || {};
          const quoteSnippet = raw.quote
            ? `<div style="margin-top:6px;padding-top:6px;border-top:1px solid rgba(255,255,255,0.12);color:#94A3B8;max-width:260px;white-space:normal;line-height:1.45;">P${escapeHtml(raw.page || "--")}: ${escapeHtml(String(raw.quote).slice(0, 90))}${String(raw.quote).length > 90 ? "..." : ""}</div>`
            : "";

          return `
            <div style="font-size:11px;line-height:1.6;">
              <div style="font-weight:700;color:#FFFFFF;margin-bottom:2px;">${escapeHtml(p.name)}</div>
              <div>标准数值：<b style="color:#60A5FA;">${formatNumber(p.value)}</b> ${escapeHtml(raw.std_unit || "")}</div>
              <div style="color:#CBD5E1;">披露原值：${formatNumber(raw.raw_value)} ${escapeHtml(raw.raw_unit || "")}</div>
              ${quoteSnippet}
            </div>
          `;
        }
      },
      grid: { left: 64, right: 24, bottom: 28, top: 20 },
      xAxis: {
        type: "category",
        data: years.map(y => `${y}年`),
        axisTick: { show: false },
        axisLine: { lineStyle: { color: isDark ? "#334155" : "#E2E8F0" } },
        axisLabel: { color: isDark ? "#94A3B8" : "#64748B", fontSize: 11, fontWeight: 600 }
      },
      yAxis: {
        type: "value",
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: isDark ? "#1E293B" : "#F1F5F9", type: "dashed" } },
        axisLabel: {
          color: isDark ? "#94A3B8" : "#64748B",
          fontSize: 11,
          formatter: (val) => {
            if (Math.abs(val) >= 100000000) return `${(val / 100000000).toFixed(1)}亿`;
            if (Math.abs(val) >= 10000) return `${(val / 10000).toFixed(0)}万`;
            return Number(val).toLocaleString();
          }
        }
      },
      series: [
        {
          name: compName,
          type: "line",
          data: seriesData,
          smooth: 0.3,
          symbol: "circle",
          symbolSize: 8,
          lineStyle: { width: 2.5, color: "#2563EB" },
          connectNulls: true,
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "rgba(37, 99, 235, 0.16)" },
              { offset: 1, color: "rgba(37, 99, 235, 0.0)" }
            ])
          }
        }
      ]
    };

    trendChartInstance.setOption(option, true);
  }

  function renderCompanyAccordions(kpis, activeIndicatorCode) {
    const container = document.getElementById("company-kpi-accordions");
    if (!container) return;
    container.innerHTML = "";

    const activeCode = activeIndicatorCode || trendIndicatorSelect.value;

    const dimensionDefs = [
      { match: "环境", badge: "E", badgeCls: "bg-emerald-50 text-emerald-700 border-emerald-200", label: "环境" },
      { match: "社会", badge: "S", badgeCls: "bg-blue-50 text-blue-700 border-blue-200", label: "社会" },
      { match: "治理", badge: "G", badgeCls: "bg-indigo-50 text-indigo-700 border-indigo-200", label: "治理" }
    ];

    dimensionDefs.forEach((dDef, idx) => {
      const items = kpis.filter(k => (k.dimension || "").includes(dDef.match));
      if (items.length === 0) return;

      const disclosedCount = items.filter(it => {
        if (it.status === "未披露" || it.audit_status === "未披露") return false;
        if (it.std_unit === "类别字段" || it.indicator_code === "Q30") {
          return Boolean(it.quote || it.std_value !== null);
        }
        return it.std_value !== null && it.std_value !== undefined;
      }).length;

      const accDiv = document.createElement("div");
      accDiv.className = "border border-slate-200/90 rounded-xl overflow-hidden bg-white";

      const containsActive = items.some(item => item.indicator_code === activeCode);
      const isDefaultOpen = containsActive || idx === 0;

      const headDiv = document.createElement("div");
      headDiv.className = "px-4 py-3 bg-slate-50/70 hover:bg-slate-100/70 cursor-pointer flex items-center justify-between transition select-none border-b border-slate-100";
      headDiv.innerHTML = `
        <div class="flex items-center space-x-2.5">
          <i class="ph ph-caret-down text-slate-400 text-xs acc-icon ${isDefaultOpen ? "" : "-rotate-90"}"></i>
          <span class="w-5 h-5 rounded text-[11px] font-bold font-mono flex items-center justify-center border ${dDef.badgeCls}">${dDef.badge}</span>
          <span class="font-bold text-xs text-slate-900">${dDef.label}</span>
          <span class="text-[11px] text-slate-400 font-mono">${items.length} 项</span>
        </div>
        <span class="text-[11px] text-slate-400 font-mono">已披露 ${disclosedCount}/${items.length}</span>
      `;

      const bodyDiv = document.createElement("div");
      bodyDiv.className = `acc-body ${isDefaultOpen ? "" : "hidden"} divide-y divide-slate-100`;

      items.forEach(item => {
        const isActive = item.indicator_code === activeCode;
        const isUndisclosed = item.status === "未披露" || item.audit_status === "未披露";
        const isQual = !isUndisclosed && (item.std_unit === "类别字段" || item.indicator_code === "Q30");

        let valHtml = "";
        if (isUndisclosed) {
          valHtml = `<span class="text-xs text-slate-300">未披露</span>`;
        } else if (isQual) {
          const qualText = item.conv_note || item.raw_unit || "未附独立鉴证";
          valHtml = `<span class="text-xs font-semibold text-slate-700">${escapeHtml(qualText)}</span>`;
        } else if (item.std_value !== null && item.std_value !== undefined) {
          valHtml = `<span class="font-mono font-bold text-slate-900 text-xs sm:text-sm">${formatNumber(item.std_value)}</span> <span class="text-[11px] text-slate-400 ml-0.5">${escapeHtml(item.std_unit || "")}</span>`;
        } else {
          valHtml = `<span class="text-xs text-slate-300">未披露</span>`;
        }

        const pageHtml = item.page
          ? `<span class="hidden sm:inline-block font-mono text-[11px] text-slate-400 w-10 text-right">P${escapeHtml(item.page)}</span>`
          : `<span class="hidden sm:inline-block w-10"></span>`;

        const quoteBtnHtml = item.quote
          ? `<button type="button" class="btn-comp-row-quote p-1.5 rounded-lg text-slate-400 hover:text-blue-600 hover:bg-blue-50 transition cursor-pointer" title="查看报告原文摘录">
              <i class="ph ph-quotes text-sm"></i>
            </button>`
          : "";

        const row = document.createElement("div");
        row.className = `kpi-row-item px-4 py-2.5 flex items-center justify-between gap-3 cursor-pointer text-xs ${
          isActive ? "kpi-row-active" : ""
        }`;

        row.innerHTML = `
          <div class="flex items-center space-x-3 min-w-0">
            <span class="font-mono font-bold text-[11px] ${isActive ? "text-blue-600" : "text-slate-400"} w-9 flex-shrink-0">${escapeHtml(item.indicator_code)}</span>
            <span class="font-medium ${isActive ? "text-blue-900 font-semibold" : "text-slate-700"} truncate">${escapeHtml(item.indicator_name)}</span>
          </div>
          <div class="flex items-center space-x-2.5 flex-shrink-0">
            <div class="text-right">${valHtml}</div>
            ${pageHtml}
            ${quoteBtnHtml}
            <span class="w-7 h-7 rounded-lg flex items-center justify-center transition ${
              isActive ? "bg-blue-600 text-white shadow-xs" : "bg-slate-100 text-slate-500 group-hover:text-blue-600"
            }" title="在上方图表中查看历年趋势">
              <i class="ph ph-trend-up text-xs"></i>
            </span>
          </div>
        `;

        const quoteBtn = row.querySelector(".btn-comp-row-quote");
        if (quoteBtn) {
          quoteBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            showEvidenceModal({
              name: item.indicator_name,
              page: item.page,
              quote: item.quote,
              verified_in_page: Boolean(item.verified_in_page)
            });
          });
        }

        row.addEventListener("click", () => {
          const code = item.indicator_code;
          if (trendIndicatorSelect) trendIndicatorSelect.value = code;
          loadCompanyTrend(currentCompanyCode, code);
          const chartBox = document.getElementById("echarts-trend-chart");
          if (chartBox) {
            const rect = chartBox.getBoundingClientRect();
            if (rect.top < 72) {
              document.getElementById("company-detail-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
            }
          }
        });

        bodyDiv.appendChild(row);
      });

      headDiv.addEventListener("click", () => {
        bodyDiv.classList.toggle("hidden");
        const icon = headDiv.querySelector(".acc-icon");
        if (icon) icon.classList.toggle("-rotate-90");
      });

      accDiv.appendChild(headDiv);
      accDiv.appendChild(bodyDiv);
      container.appendChild(accDiv);
    });

    const btnCompExpandAll = document.getElementById("btn-comp-expand-all");
    const btnCompCollapseAll = document.getElementById("btn-comp-collapse-all");
    if (btnCompExpandAll) {
      btnCompExpandAll.onclick = () => {
        document.querySelectorAll("#company-kpi-accordions .acc-body").forEach(b => b.classList.remove("hidden"));
        document.querySelectorAll("#company-kpi-accordions .acc-icon").forEach(i => i.classList.remove("-rotate-90"));
      };
    }
    if (btnCompCollapseAll) {
      btnCompCollapseAll.onclick = () => {
        document.querySelectorAll("#company-kpi-accordions .acc-body").forEach(b => b.classList.add("hidden"));
        document.querySelectorAll("#company-kpi-accordions .acc-icon").forEach(i => i.classList.add("-rotate-90"));
      };
    }
  }

  // ==================== 3. 报告库列表视图 (Reports) ====================
  const reportsTbody = document.getElementById("reports-tbody");
  const reportsStatusFilter = document.getElementById("reports-status-filter");
  const reportsSearchInput = document.getElementById("reports-search-input");
  const reportsSearchClear = document.getElementById("reports-search-clear");
  let currentReportYearFilter = "";

  document.querySelectorAll(".rep-filter-year").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".rep-filter-year").forEach(b => {
        b.classList.remove("active", "bg-white", "text-slate-900", "shadow-xs", "font-semibold");
        b.classList.add("text-slate-600", "font-medium");
      });
      btn.classList.add("active", "bg-white", "text-slate-900", "shadow-xs", "font-semibold");
      btn.classList.remove("text-slate-600", "font-medium");
      currentReportYearFilter = btn.getAttribute("data-year");
      loadReportsView();
    });
  });

  if (reportsStatusFilter) reportsStatusFilter.addEventListener("change", () => loadReportsView());
  if (reportsSearchInput) {
    reportsSearchInput.addEventListener("input", () => {
      if (reportsSearchClear) {
        reportsSearchClear.classList.toggle("hidden", !reportsSearchInput.value);
      }
      loadReportsView();
    });
  }
  if (reportsSearchClear) {
    reportsSearchClear.addEventListener("click", () => {
      reportsSearchInput.value = "";
      reportsSearchClear.classList.add("hidden");
      loadReportsView();
    });
  }

  function loadReportsView() {
    let url = "/api/reports?";
    if (currentReportYearFilter) url += `year=${currentReportYearFilter}&`;
    const kw = reportsSearchInput ? reportsSearchInput.value.trim() : "";
    if (kw) url += `keyword=${encodeURIComponent(kw)}&`;
    if (reportsStatusFilter && reportsStatusFilter.value && reportsStatusFilter.value !== "全部") {
      url += `status=${encodeURIComponent(reportsStatusFilter.value)}&`;
    }

    fetch(url)
      .then(r => r.json())
      .then(d => {
        const list = d.reports || [];
        const countBadge = document.getElementById("reports-count-badge");
        if (countBadge) countBadge.textContent = `共 ${list.length} 份`;

        reportsTbody.innerHTML = "";
        if (list.length === 0) {
          reportsTbody.innerHTML = '<tr><td colspan="7" class="py-12 text-center text-slate-400 text-xs">未找到符合筛选条件的报告</td></tr>';
          return;
        }

        list.forEach(r => {
          const tr = document.createElement("tr");
          tr.className = "border-b border-slate-100";

          let statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium bg-slate-100 text-slate-600">官方披露</span>';
          if (r.status === "已人工核对") {
            statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/80">已人工复核</span>';
          } else if (isAdmin) {
            statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium bg-amber-50 text-amber-700 border border-amber-200/80">待复核</span>';
          }

          tr.innerHTML = `
            <td class="py-3 px-4 font-mono font-semibold text-slate-500">${escapeHtml(r.company_code)}</td>
            <td class="py-3 px-4 whitespace-nowrap">
              <button class="btn-rep-jump-comp font-semibold text-slate-900 hover:text-blue-600 transition cursor-pointer text-left" data-code="${escapeHtml(r.company_code)}">${escapeHtml(r.company_name)}</button>
            </td>
            <td class="py-3 px-4 font-mono text-slate-700 font-semibold">${escapeHtml(r.year)}</td>
            <td class="py-3 px-4">
              <button class="btn-go-report-detail text-slate-700 hover:text-blue-600 font-medium transition cursor-pointer text-left" data-id="${r.id}">${escapeHtml(r.title)}</button>
            </td>
            <td class="py-3 px-4 text-center font-mono text-slate-500 whitespace-nowrap">${Number(r.total_pages || 0)} 页</td>
            <td class="py-3 px-4 text-center whitespace-nowrap">${statusBadge}</td>
            <td class="py-3 px-4 text-right space-x-1.5 whitespace-nowrap">
              <button class="btn-go-report-detail px-2.5 py-1 rounded-lg bg-blue-50 hover:bg-blue-100/80 text-blue-700 font-semibold transition inline-flex items-center space-x-1 cursor-pointer" data-id="${r.id}">
                <span>指标详情</span>
              </button>
              <button class="btn-export-clean-data-rep px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200/80 text-slate-700 font-medium transition inline-flex items-center space-x-1 cursor-pointer" data-id="${r.id}" title="导出 Excel 数据">
                <i class="ph ph-file-xls"></i>
                <span>导出数据</span>
              </button>
              ${isAdmin ? `<button class="btn-export-annotation-rep px-2.5 py-1 rounded-lg bg-emerald-50 hover:bg-emerald-100 text-emerald-700 font-medium transition inline-flex items-center space-x-1 cursor-pointer" data-id="${r.id}" title="管理员导出核验底稿">
                <span>导出底稿</span>
              </button>` : ""}
              ${r.has_pdf ? `<button class="btn-download-pdf-rep px-2.5 py-1 rounded-lg bg-rose-50 hover:bg-rose-100/80 text-rose-700 font-medium transition inline-flex items-center space-x-1 cursor-pointer" data-id="${r.id}" title="下载原版 PDF">
                <i class="ph ph-file-pdf"></i>
                <span>PDF</span>
              </button>` : ""}
            </td>
          `;
          reportsTbody.appendChild(tr);
        });

        reportsTbody.querySelectorAll(".btn-rep-jump-comp").forEach(btn => {
          btn.addEventListener("click", () => navigateToCompany(btn.getAttribute("data-code")));
        });

        reportsTbody.querySelectorAll(".btn-go-report-detail").forEach(btn => {
          btn.addEventListener("click", () => openReportDetailPage(btn.getAttribute("data-id")));
        });

        reportsTbody.querySelectorAll(".btn-export-clean-data-rep").forEach(btn => {
          btn.addEventListener("click", () => {
            window.open(`/api/reports/${btn.getAttribute("data-id")}/export-data`, "_blank");
          });
        });

        reportsTbody.querySelectorAll(".btn-export-annotation-rep").forEach(btn => {
          btn.addEventListener("click", () => {
            const repId = btn.getAttribute("data-id");
            const token = sessionStorage.getItem("esg_admin_token") || "";
            window.open(`/api/annotation/export/${repId}?token=${encodeURIComponent(token)}`, "_blank");
          });
        });

        reportsTbody.querySelectorAll(".btn-download-pdf-rep").forEach(btn => {
          btn.addEventListener("click", () => {
            window.open(`/api/reports/${btn.getAttribute("data-id")}/download-pdf`, "_blank");
          });
        });
      });
  }

  // ==================== 4. 报告指标详情页 ====================
  const detailBtnGoCompany = document.getElementById("detail-btn-go-company");
  if (detailBtnGoCompany) {
    detailBtnGoCompany.addEventListener("click", () => {
      if (currentReportCompanyCode) navigateToCompany(currentReportCompanyCode);
    });
  }

  function openReportDetailPage(reportId) {
    currentReportDetailId = reportId;
    fetch(`/api/reports/${reportId}`)
      .then(r => r.json())
      .then(d => {
        const rep = d.report;
        currentReportCompanyCode = rep.company_code;

        document.getElementById("rep-page-title").textContent = rep.title;
        document.getElementById("rep-page-code").textContent = rep.company_code;
        document.getElementById("rep-page-desc").textContent = `${rep.company_name} · ${rep.year}年度报告`;
        document.getElementById("rep-page-total-pages").textContent = `${rep.total_pages} 页`;
        document.getElementById("rep-page-disclosure-rate").textContent = rep.disclosure_rate;

        const badgeSpan = document.getElementById("rep-page-status-badge");
        if (badgeSpan) {
          if (rep.status === "已人工核对") {
            badgeSpan.className = "inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/80";
            badgeSpan.textContent = "已人工复核";
          } else {
            badgeSpan.className = "inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-slate-100 text-slate-600";
            badgeSpan.textContent = "官方披露";
          }
        }

        const detailBtnExportData = document.getElementById("detail-btn-export-data");
        if (detailBtnExportData) {
          detailBtnExportData.onclick = () => {
            window.open(`/api/reports/${reportId}/export-data`, "_blank");
          };
        }

        const detailBtnExportWorkpaper = document.getElementById("detail-btn-export-workpaper");
        if (detailBtnExportWorkpaper) {
          if (isAdmin) {
            detailBtnExportWorkpaper.classList.remove("hidden");
            detailBtnExportWorkpaper.onclick = () => {
              const token = sessionStorage.getItem("esg_admin_token") || "";
              window.open(`/api/annotation/export/${reportId}?token=${encodeURIComponent(token)}`, "_blank");
            };
          } else {
            detailBtnExportWorkpaper.classList.add("hidden");
          }
        }

        const btnDownloadPdf = document.getElementById("detail-btn-download-pdf");
        if (btnDownloadPdf) {
          if (rep.has_pdf) {
            btnDownloadPdf.style.display = "inline-flex";
            btnDownloadPdf.onclick = () => {
              window.open(`/api/reports/${reportId}/download-pdf`, "_blank");
            };
          } else {
            btnDownloadPdf.style.display = "none";
          }
        }

        // 重置回默认「标准指标」标签页
        document.querySelectorAll(".rep-detail-tab-btn").forEach(b => {
          const isStd = b.getAttribute("data-target") === "rep-page-tab-standard";
          b.classList.toggle("active", isStd);
          b.classList.toggle("border-blue-600", isStd);
          b.classList.toggle("text-blue-600", isStd);
          b.classList.toggle("border-transparent", !isStd);
          b.classList.toggle("text-slate-500", !isStd);
        });
        document.getElementById("rep-page-tab-standard")?.classList.remove("hidden");
        document.getElementById("rep-page-tab-raw")?.classList.add("hidden");
        document.getElementById("rep-detail-acc-controls")?.classList.remove("hidden");

        renderReportStandardKpis(d.standard_kpis || []);
        renderReportRawKpis(d.raw_kpis || []);
        switchView("view-report-detail");
      });
  }

  function renderReportStandardKpis(kpis) {
    const container = document.getElementById("rep-page-tab-standard");
    if (!container) return;
    container.innerHTML = "";

    const dimensionDefs = [
      { match: "环境", badge: "E", badgeCls: "bg-emerald-50 text-emerald-700 border-emerald-200", label: "环境" },
      { match: "社会", badge: "S", badgeCls: "bg-blue-50 text-blue-700 border-blue-200", label: "社会" },
      { match: "治理", badge: "G", badgeCls: "bg-indigo-50 text-indigo-700 border-indigo-200", label: "治理" }
    ];

    dimensionDefs.forEach(dDef => {
      const items = kpis.filter(k => (k.dimension || "").includes(dDef.match));
      if (items.length === 0) return;

      const accDiv = document.createElement("div");
      accDiv.className = "border border-slate-200/90 rounded-xl overflow-hidden bg-white";

      const headDiv = document.createElement("div");
      headDiv.className = "px-4 py-3 bg-slate-50/70 hover:bg-slate-100/70 cursor-pointer flex items-center justify-between transition select-none border-b border-slate-100";
      headDiv.innerHTML = `
        <div class="flex items-center space-x-2.5">
          <i class="ph ph-caret-down text-slate-400 text-xs acc-icon"></i>
          <span class="w-5 h-5 rounded text-[11px] font-bold font-mono flex items-center justify-center border ${dDef.badgeCls}">${dDef.badge}</span>
          <span class="font-bold text-xs text-slate-900">${dDef.label}</span>
          <span class="text-[11px] text-slate-400 font-mono">${items.length} 项</span>
        </div>
      `;

      const bodyDiv = document.createElement("div");
      bodyDiv.className = "acc-body overflow-x-auto";

      const rowsHtml = items.map(k => {
        const isUndisclosed = k.status === "未披露" || k.audit_status === "未披露" || (k.std_value === null && !k.quote);
        const verifyBadge = isUndisclosed
          ? '<span class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-50 text-slate-400 border border-slate-200/70">未披露</span>'
          : (k.verified_in_page
              ? '<span class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/80">已匹配</span>'
              : '<span class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-500">待核</span>');

        let stdValDisplay = k.std_value !== null && k.std_value !== undefined
          ? formatNumber(k.std_value)
          : '<span class="text-slate-300">--</span>';
        let stdUnitDisplay = escapeHtml(k.std_unit || "--");
        if (!isUndisclosed && (k.std_unit === "类别字段" || k.indicator_code === "Q30")) {
          stdValDisplay = `<span class="text-xs font-semibold text-slate-700">${escapeHtml(k.conv_note || k.raw_unit || "未附独立鉴证")}</span>`;
          stdUnitDisplay = '<span class="text-[11px] text-slate-400">定性</span>';
        }

        return `
          <tr class="border-b border-slate-100 text-xs">
            <td class="py-2.5 px-3 font-mono font-bold text-slate-500 w-16">${escapeHtml(k.indicator_code)}</td>
            <td class="py-2.5 px-3 font-medium text-slate-800">${escapeHtml(k.indicator_name)}</td>
            <td class="py-2.5 px-3 text-right font-mono font-bold text-blue-700 whitespace-nowrap">${stdValDisplay}</td>
            <td class="py-2.5 px-3 text-slate-500 whitespace-nowrap">${stdUnitDisplay}</td>
            <td class="py-2.5 px-3 text-slate-500 text-[11px]">${escapeHtml(k.conv_note || "--")}</td>
            <td class="py-2.5 px-3 text-center font-mono text-slate-500 whitespace-nowrap">${k.page ? `P${escapeHtml(k.page)}` : "--"}</td>
            <td class="py-2.5 px-3 text-center whitespace-nowrap">${verifyBadge}</td>
            <td class="py-2.5 px-3 text-center whitespace-nowrap">
              ${k.quote ? `<button class="btn-rep-evidence text-blue-600 hover:text-blue-800 font-medium inline-flex items-center space-x-1 cursor-pointer" data-quote="${encodeURIComponent(k.quote)}" data-name="${escapeHtml(k.indicator_name)}" data-page="${escapeHtml(k.page || "")}" data-verified="${k.verified_in_page}"><i class="ph ph-quotes"></i><span>查看</span></button>` : '<span class="text-slate-300">--</span>'}
            </td>
          </tr>
        `;
      }).join("");

      bodyDiv.innerHTML = `
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="bg-slate-50/50 text-slate-500 text-[11px] font-semibold border-b border-slate-100">
              <th class="py-2 px-3">代码</th>
              <th class="py-2 px-3">指标名称</th>
              <th class="py-2 px-3 text-right">标准化数值</th>
              <th class="py-2 px-3">单位</th>
              <th class="py-2 px-3">备注说明</th>
              <th class="py-2 px-3 text-center">页码</th>
              <th class="py-2 px-3 text-center">原文核验</th>
              <th class="py-2 px-3 text-center">摘录</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>
      `;

      headDiv.addEventListener("click", () => {
        bodyDiv.classList.toggle("hidden");
        const icon = headDiv.querySelector(".acc-icon");
        if (icon) icon.classList.toggle("-rotate-90");
      });

      accDiv.appendChild(headDiv);
      accDiv.appendChild(bodyDiv);
      container.appendChild(accDiv);
    });

    const btnRepExpandAll = document.getElementById("btn-rep-expand-all");
    const btnRepCollapseAll = document.getElementById("btn-rep-collapse-all");
    if (btnRepExpandAll) {
      btnRepExpandAll.onclick = () => {
        document.querySelectorAll("#rep-page-tab-standard .acc-body").forEach(b => b.classList.remove("hidden"));
        document.querySelectorAll("#rep-page-tab-standard .acc-icon").forEach(i => i.classList.remove("-rotate-90"));
      };
    }
    if (btnRepCollapseAll) {
      btnRepCollapseAll.onclick = () => {
        document.querySelectorAll("#rep-page-tab-standard .acc-body").forEach(b => b.classList.add("hidden"));
        document.querySelectorAll("#rep-page-tab-standard .acc-icon").forEach(i => i.classList.add("-rotate-90"));
      };
    }

    container.querySelectorAll(".btn-rep-evidence").forEach(btn => {
      btn.addEventListener("click", () => {
        showEvidenceModal({
          name: btn.getAttribute("data-name"),
          page: btn.getAttribute("data-page"),
          quote: decodeURIComponent(btn.getAttribute("data-quote")),
          verified_in_page: btn.getAttribute("data-verified") === "1" || btn.getAttribute("data-verified") === "true"
        });
      });
    });
  }

  function renderReportRawKpis(rawKpis) {
    const tbody = document.getElementById("rep-page-raw-kpis-tbody");
    if (!tbody) return;
    tbody.innerHTML = "";
    rawKpis.forEach(k => {
      const tr = document.createElement("tr");
      tr.className = "border-b border-slate-100 text-xs";
      tr.innerHTML = `
        <td class="py-2.5 px-3 font-mono font-bold text-slate-500">${escapeHtml(k.code)}</td>
        <td class="py-2.5 px-3 font-medium text-slate-800">${escapeHtml(k.raw_name)}</td>
        <td class="py-2.5 px-3 text-right font-mono text-slate-900 font-semibold">${k.raw_value !== null && k.raw_value !== undefined ? formatNumber(k.raw_value) : "--"}</td>
        <td class="py-2.5 px-3 text-slate-500">${escapeHtml(k.raw_unit || "--")}</td>
        <td class="py-2.5 px-3 text-center font-mono text-slate-600">${escapeHtml(k.year)}</td>
        <td class="py-2.5 px-3 text-center font-mono text-slate-500">${k.page ? `P${escapeHtml(k.page)}` : "--"}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  document.querySelectorAll(".rep-detail-tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".rep-detail-tab-btn").forEach(b => {
        b.classList.remove("active", "border-blue-600", "text-blue-600");
        b.classList.add("border-transparent", "text-slate-500");
      });
      btn.classList.add("active", "border-blue-600", "text-blue-600");
      btn.classList.remove("border-transparent", "text-slate-500");

      document.querySelectorAll(".rep-detail-tab-content").forEach(c => c.classList.add("hidden"));
      const targetId = btn.getAttribute("data-target");
      document.getElementById(targetId)?.classList.remove("hidden");

      const accControls = document.getElementById("rep-detail-acc-controls");
      if (accControls) {
        accControls.classList.toggle("hidden", targetId !== "rep-page-tab-standard");
      }
    });
  });

  // ==================== 5. 行业排名视图 (Rankings) ====================
  const rankingIndicatorSelect = document.getElementById("ranking-indicator-select");
  const rankingYearSelect = document.getElementById("ranking-year-select");
  const rankingIndustrySelect = document.getElementById("ranking-industry-select");
  const rankingSortSelect = document.getElementById("ranking-sort-select");
  const rankingsTbody = document.getElementById("rankings-tbody");

  if (rankingIndicatorSelect) rankingIndicatorSelect.addEventListener("change", () => loadRankingsView());
  if (rankingYearSelect) rankingYearSelect.addEventListener("change", () => loadRankingsView());
  if (rankingIndustrySelect) rankingIndustrySelect.addEventListener("change", () => renderRankingsRows());
  if (rankingSortSelect) rankingSortSelect.addEventListener("change", () => renderRankingsRows());

  function loadRankingsView() {
    if (!rankingIndicatorSelect || !rankingYearSelect || !rankingsTbody) return;
    const ind = rankingIndicatorSelect.value;
    const year = rankingYearSelect.value;
    const indText = rankingIndicatorSelect.options[rankingIndicatorSelect.selectedIndex]?.text || ind;

    const titleEl = document.getElementById("ranking-table-title");
    if (titleEl) titleEl.textContent = `${year}年度 · ${indText}`;

    fetch(`/api/rankings?indicator_code=${encodeURIComponent(ind)}&year=${encodeURIComponent(year)}`)
      .then(r => r.json())
      .then(d => {
        cachedRankingsData = d.rankings || [];
        renderRankingsRows();
      });
  }

  function renderRankingsRows() {
    if (!rankingsTbody) return;
    const indCode = rankingIndicatorSelect ? rankingIndicatorSelect.value : "Q01";
    const indFilter = rankingIndustrySelect ? rankingIndustrySelect.value : "全部";
    const sortDir = rankingSortSelect ? rankingSortSelect.value : "desc";

    let list = [...cachedRankingsData];
    if (indFilter && indFilter !== "全部") {
      list = list.filter(r => (r.industry || "").includes(indFilter));
    }

    list.sort((a, b) => {
      const va = Number(a.std_value || 0);
      const vb = Number(b.std_value || 0);
      return sortDir === "asc" ? va - vb : vb - va;
    });

    const countBadge = document.getElementById("ranking-count-badge");
    if (countBadge) countBadge.textContent = `共 ${list.length} 家企业`;

    rankingsTbody.innerHTML = "";
    if (list.length === 0) {
      rankingsTbody.innerHTML = '<tr><td colspan="6" class="py-12 text-center text-slate-400 text-xs">当前筛选条件下暂无已披露数据</td></tr>';
      return;
    }

    const maxVal = Math.max(...list.map(r => Math.abs(Number(r.std_value || 0))), 0);

    list.forEach((r, idx) => {
      const tr = document.createElement("tr");
      tr.className = "border-b border-slate-100 cursor-pointer group";

      let rankBadge = `<span class="font-semibold text-slate-500 font-mono">${idx + 1}</span>`;
      if (idx === 0) rankBadge = '<span class="w-6 h-6 rounded-full bg-amber-400 text-white font-bold flex items-center justify-center mx-auto text-xs">1</span>';
      if (idx === 1) rankBadge = '<span class="w-6 h-6 rounded-full bg-slate-300 text-slate-800 font-bold flex items-center justify-center mx-auto text-xs">2</span>';
      if (idx === 2) rankBadge = '<span class="w-6 h-6 rounded-full bg-amber-600/85 text-white font-bold flex items-center justify-center mx-auto text-xs">3</span>';

      const pct = maxVal > 0 ? Math.min(100, (Math.abs(Number(r.std_value || 0)) / maxVal) * 100).toFixed(1) : 0;

      const isVerified = r.audit_status === "已人工核对" || r.audit_status === "人工已修正";
      let statusBadge = '<span class="px-2 py-0.5 rounded-md text-[11px] bg-slate-100 text-slate-600 font-medium">官方披露</span>';
      if (isVerified) {
        statusBadge = '<span class="px-2 py-0.5 rounded-md text-[11px] bg-emerald-50 text-emerald-700 font-semibold border border-emerald-200/80">已人工复核</span>';
      } else if (isAdmin) {
        statusBadge = '<span class="px-2 py-0.5 rounded-md text-[11px] bg-amber-50 text-amber-700 font-medium border border-amber-200/80">待复核</span>';
      }

      tr.innerHTML = `
        <td class="py-3 px-4 text-center">${rankBadge}</td>
        <td class="py-3 px-4 font-semibold text-slate-900 group-hover:text-blue-600 transition whitespace-nowrap">
          <span>${escapeHtml(r.company_name)}</span>
          <span class="font-mono text-[11px] text-slate-400 ml-1.5">${escapeHtml(r.company_code)}</span>
        </td>
        <td class="py-3 px-4 text-slate-500 whitespace-nowrap">${escapeHtml(r.industry)}</td>
        <td class="py-3 px-4 text-right font-mono font-bold text-blue-700 whitespace-nowrap">${formatNumber(r.std_value)} <span class="text-slate-400 font-normal text-[11px]">${escapeHtml(r.std_unit)}</span></td>
        <td class="py-3 px-4 text-center whitespace-nowrap">${statusBadge}</td>
        <td class="py-3 px-4">
          <div class="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden">
            <div class="bg-blue-600 h-1.5 rounded-full transition-all duration-300" style="width: ${pct}%"></div>
          </div>
        </td>
      `;

      tr.addEventListener("click", () => navigateToCompany(r.company_code, indCode));
      rankingsTbody.appendChild(tr);
    });
  }

  // ==================== 6. 人工标注底稿导入同步 (管理员专属) ====================
  const annotationFileInput = document.getElementById("annotation-file-input");
  const adminImportBtnLabel = document.getElementById("admin-import-btn-label");

  if (annotationFileInput) {
    annotationFileInput.addEventListener("change", async (e) => {
      if (!e.target.files || e.target.files.length === 0) return;
      const file = e.target.files[0];

      const formData = new FormData();
      formData.append("file", file);

      try {
        const token = sessionStorage.getItem("esg_admin_token") || "";
        if (adminImportBtnLabel) adminImportBtnLabel.textContent = "同步中...";
        const resp = await fetch("/api/annotation/import", {
          method: "POST",
          headers: { "X-Admin-Token": token },
          body: formData
        });
        const res = await resp.json();

        if (!resp.ok) {
          showToast("底稿导入失败：" + (res.detail || "请检查登录状态或文件格式"), "error");
          return;
        }

        showToast(
          `核验底稿已同步生效\n处理 ${res.total_processed} 条 · 确认 ${res.records_updated} 条 · 修正 ${res.records_corrected} 条`,
          "success"
        );

        loadCompaniesView();
        loadReportsView();
        loadRankingsView();
        loadStats();
      } catch (err) {
        showToast(`底稿导入异常：${err.message}`, "error");
      } finally {
        if (adminImportBtnLabel) adminImportBtnLabel.textContent = "导入核验底稿";
        e.target.value = "";
      }
    });
  }

  // ==================== 7. 智能抽取 (Smart Extraction) ====================
  const sampleSelect = document.getElementById("sample-select");
  const fileInput = document.getElementById("file-input");
  const dropzone = document.getElementById("dropzone");
  const uploadHint = document.getElementById("upload-hint");
  const selectedFileBar = document.getElementById("selected-file-bar");
  const selectedFileName = document.getElementById("selected-file-name");
  const btnClearFile = document.getElementById("btn-clear-file");
  const btnStart = document.getElementById("btn-start");
  const btnExportExcel = document.getElementById("btn-export-excel");
  const progressContainer = document.getElementById("progress-container");
  const progressText = document.getElementById("progress-text");
  const progressPct = document.getElementById("progress-pct");
  const progressBar = document.getElementById("progress-bar");
  const resultContainer = document.getElementById("result-container");
  const auditDimFilters = document.getElementById("audit-dim-filters");
  let samplesLoaded = false;

  function updateSelectedFileUI(file) {
    selectedFile = file || null;
    if (selectedFile) {
      const sizeMb = (selectedFile.size / 1024 / 1024).toFixed(2);
      if (uploadHint) uploadHint.textContent = "已准备就绪，点击右侧「开始提取」启动解析";
      if (selectedFileName) selectedFileName.textContent = `${selectedFile.name} (${sizeMb} MB)`;
      if (selectedFileBar) selectedFileBar.classList.remove("hidden");
      if (sampleSelect) sampleSelect.value = "";
    } else {
      if (fileInput) fileInput.value = "";
      if (uploadHint) uploadHint.textContent = "点击选择或拖拽 PDF 报告文件至此处";
      if (selectedFileBar) selectedFileBar.classList.add("hidden");
    }
  }

  function loadSamples() {
    if (samplesLoaded || !sampleSelect) return;
    fetch("/api/samples")
      .then(r => r.json())
      .then(data => {
        const prevVal = sampleSelect.value;
        sampleSelect.innerHTML = '<option value="">-- 选择示例报告直接测试 --</option>';
        (data.samples || []).forEach(s => {
          const opt = document.createElement("option");
          opt.value = s.filename;
          opt.textContent = `${s.filename} (${s.size_mb} MB)`;
          sampleSelect.appendChild(opt);
        });
        if (prevVal) sampleSelect.value = prevVal;
        samplesLoaded = true;
      })
      .catch(() => {});
  }

  loadSamples();

  if (sampleSelect) {
    sampleSelect.addEventListener("change", () => {
      if (sampleSelect.value) {
        updateSelectedFileUI(null);
      }
    });
  }

  if (btnClearFile) {
    btnClearFile.addEventListener("click", (e) => {
      e.stopPropagation();
      updateSelectedFileUI(null);
    });
  }

  // 智能抽取结果页标签切换
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => {
        b.classList.remove("active", "border-blue-600", "text-blue-600");
        b.classList.add("border-transparent", "text-slate-500");
      });
      btn.classList.add("active", "border-blue-600", "text-blue-600");
      btn.classList.remove("border-transparent", "text-slate-500");

      document.querySelectorAll(".tab-content").forEach(c => c.classList.add("hidden"));
      const targetId = btn.getAttribute("data-target");
      document.getElementById(targetId)?.classList.remove("hidden");

      if (auditDimFilters) {
        auditDimFilters.classList.toggle("hidden", targetId !== "tab-workpaper");
      }
    });
  });

  // 抽取结果维度筛选胶囊
  document.querySelectorAll(".audit-dim-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".audit-dim-btn").forEach(b => {
        b.classList.remove("active", "bg-slate-900", "text-white", "font-semibold");
        b.classList.add("bg-slate-100", "text-slate-600", "font-medium");
      });
      btn.classList.add("active", "bg-slate-900", "text-white", "font-semibold");
      btn.classList.remove("bg-slate-100", "text-slate-600", "font-medium");
      currentAuditDimFilter = btn.getAttribute("data-dim") || "all";
      if (currentAnalysis) renderAuditIndicatorsTable(currentAnalysis.indicators || []);
    });
  });

  if (dropzone) {
    dropzone.addEventListener("click", () => fileInput && fileInput.click());
    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone.classList.add("border-blue-500", "bg-blue-50/40");
    });
    dropzone.addEventListener("dragleave", () => {
      dropzone.classList.remove("border-blue-500", "bg-blue-50/40");
    });
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("border-blue-500", "bg-blue-50/40");
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        updateSelectedFileUI(e.dataTransfer.files[0]);
      }
    });
  }

  if (fileInput) {
    fileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files.length > 0) {
        updateSelectedFileUI(e.target.files[0]);
      }
    });
  }

  if (btnStart) {
    btnStart.addEventListener("click", async () => {
      const sample = sampleSelect ? sampleSelect.value : "";
      if (!selectedFile && !sample) {
        showToast("请先选择一份 PDF 报告文件，或在右侧选择示例报告", "warning");
        return;
      }

      progressContainer.classList.remove("hidden");
      resultContainer.classList.add("hidden");
      btnStart.disabled = true;
      btnStart.classList.add("opacity-60", "cursor-not-allowed");

      let progress = 12;
      progressBar.style.width = "12%";
      progressPct.textContent = "12%";
      progressText.innerHTML = '<i class="ph ph-spinner animate-spin text-blue-600"></i><span>正在解析 PDF 版面结构...</span>';

      const timer = setInterval(() => {
        if (progress < 90) {
          progress += Math.floor(Math.random() * 14) + 5;
          if (progress > 90) progress = 90;
          progressBar.style.width = `${progress}%`;
          progressPct.textContent = `${progress}%`;
          if (progress > 32 && progress <= 64) {
            progressText.innerHTML = '<i class="ph ph-spinner animate-spin text-blue-600"></i><span>正在定位关键绩效表与候选页...</span>';
          } else if (progress > 64) {
            progressText.innerHTML = '<i class="ph ph-spinner animate-spin text-blue-600"></i><span>正在提取指标数值并匹配原文...</span>';
          }
        }
      }, 380);

      const formData = new FormData();
      if (selectedFile) formData.append("file", selectedFile);
      else formData.append("sample_filename", sample);

      const reqHeaders = {};
      const adminToken = sessionStorage.getItem("esg_admin_token");
      if (isAdmin && adminToken) {
        reqHeaders["X-Admin-Token"] = adminToken;
      }

      try {
        const resp = await fetch("/api/analyze", {
          method: "POST",
          headers: reqHeaders,
          body: formData
        });
        clearInterval(timer);
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(err.detail || "解析请求失败");
        }

        const data = await resp.json();
        currentAnalysis = data;
        if (adminPublishCodeInput) delete adminPublishCodeInput.dataset.reportBound;
        if (adminPublishIndustrySelect) delete adminPublishIndustrySelect.dataset.reportBound;

        progressBar.style.width = "100%";
        progressPct.textContent = "100%";
        progressText.innerHTML = '<i class="ph ph-check-circle text-emerald-600"></i><span>解析完成</span>';

        setTimeout(() => {
          renderAuditResults(data);
          refreshExtractionBanners();
          resultContainer.classList.remove("hidden");
          progressContainer.classList.add("hidden");
          btnStart.disabled = false;
          btnStart.classList.remove("opacity-60", "cursor-not-allowed");
          loadStats();
        }, 320);
      } catch (err) {
        clearInterval(timer);
        showToast(`报告解析出错：${err.message}`, "error");
        progressContainer.classList.add("hidden");
        btnStart.disabled = false;
        btnStart.classList.remove("opacity-60", "cursor-not-allowed");
      }
    });
  }

  function renderAuditIndicatorsTable(indicators) {
    const tbody = document.getElementById("indicators-tbody");
    if (!tbody) return;
    tbody.innerHTML = "";

    const filtered = indicators.filter(item => {
      if (currentAuditDimFilter === "all") return true;
      if (currentAuditDimFilter === "disclosed") {
        return item.status === "已披露" || (item.raw_value !== null && item.raw_value !== undefined);
      }
      return (item.dimension || "").includes(currentAuditDimFilter);
    });

    if (filtered.length === 0) {
      tbody.innerHTML = '<tr><td colspan="10" class="py-10 text-center text-slate-400 text-xs">当前筛选维度下暂无指标</td></tr>';
      return;
    }

    filtered.forEach(item => {
      const origIdx = indicators.indexOf(item);
      const tr = document.createElement("tr");
      tr.className = "border-b border-slate-100";

      const verifyBadge = item.verified_in_page
        ? '<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/80">已匹配</span>'
        : '<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium bg-slate-100 text-slate-500">待核</span>';

      const isDisclosed = item.status === "已披露" || (item.raw_value !== null && item.raw_value !== undefined);
      const statusBadge = isDisclosed
        ? `<span class="px-2 py-0.5 rounded-md text-[11px] font-medium bg-blue-50 text-blue-700 border border-blue-200/80">${escapeHtml(item.status || "已披露")}</span>`
        : `<span class="px-2 py-0.5 rounded-md text-[11px] font-medium bg-slate-100 text-slate-400">${escapeHtml(item.status || "未披露")}</span>`;

      const isQual = item.std_unit === "类别字段" || item.code === "Q30";
      let rawValStr = item.raw_value !== null && item.raw_value !== undefined
        ? `${formatNumber(item.raw_value)} <span class="text-slate-400 font-normal text-[11px]">${escapeHtml(item.raw_unit || "")}</span>`
        : '<span class="text-slate-300">--</span>';

      let stdValStr = item.std_value !== null && item.std_value !== undefined
        ? formatNumber(item.std_value)
        : '<span class="text-slate-300">--</span>';
      let unitStr = escapeHtml(item.std_unit || "--");

      if (isQual) {
        rawValStr = `<span class="text-slate-600 text-[11px]">${escapeHtml(item.conv_note || "--")}</span>`;
        stdValStr = `<span class="text-slate-800 font-semibold text-xs">${item.std_value === 1 ? "已鉴证" : "未鉴证"}</span>`;
        unitStr = '<span class="text-slate-400 text-[11px]">定性</span>';
      }

      tr.innerHTML = `
        <td class="py-3 px-4 font-mono font-bold text-slate-500 whitespace-nowrap">${escapeHtml(item.code)}</td>
        <td class="py-3 px-4 font-medium text-slate-900">${escapeHtml(item.name)}</td>
        <td class="py-3 px-4 text-right font-mono font-medium text-slate-700 whitespace-nowrap">${rawValStr}</td>
        <td class="py-3 px-4 text-right font-mono font-bold text-blue-700 whitespace-nowrap">${stdValStr}</td>
        <td class="py-3 px-4 text-slate-500 whitespace-nowrap">${unitStr}</td>
        <td class="py-3 px-4 text-slate-500 text-[11px]">${escapeHtml(item.conv_note || "--")}</td>
        <td class="py-3 px-4 text-center font-mono text-slate-500 whitespace-nowrap">${item.page ? `P${escapeHtml(item.page)}` : "--"}</td>
        <td class="py-3 px-4 text-center whitespace-nowrap">${verifyBadge}</td>
        <td class="py-3 px-4 text-center whitespace-nowrap">${statusBadge}</td>
        <td class="py-3 px-4 text-center whitespace-nowrap">
          ${item.quote ? `<button class="btn-view-evidence text-blue-600 hover:text-blue-800 font-medium inline-flex items-center space-x-1 cursor-pointer" data-idx="${origIdx}"><i class="ph ph-quotes"></i><span>查看</span></button>` : '<span class="text-slate-300">--</span>'}
        </td>
      `;
      tbody.appendChild(tr);
    });

    tbody.querySelectorAll(".btn-view-evidence").forEach(btn => {
      btn.addEventListener("click", () => {
        const item = indicators[Number(btn.getAttribute("data-idx"))];
        if (item) showEvidenceModal(item);
      });
    });
  }

  function renderAuditResults(data) {
    const summary = data.summary || {};
    const indicators = data.indicators || [];
    const anomalies = data.anomalies || [];

    document.getElementById("card-company").textContent = summary.company_name || "--";
    document.getElementById("card-year").textContent = `${summary.report_year || "--"}年度`;
    document.getElementById("card-analyzed-pages").textContent = summary.target_pages_analyzed ? summary.target_pages_analyzed.length : "--";
    document.getElementById("card-total-pages").textContent = summary.total_pages || "--";
    document.getElementById("card-disclosure-rate").textContent = summary.disclosure_rate || "--%";
    document.getElementById("card-disclosed-count").textContent = summary.disclosed_count ?? 0;
    document.getElementById("card-verify-rate").textContent = summary.verification_rate || "--%";
    document.getElementById("card-anomalies-count").textContent = `${summary.anomalies_count ?? anomalies.length} 项`;
    document.getElementById("tab-badge-anomalies").textContent = anomalies.length;

    if (data.excel_download_url && btnExportExcel) {
      btnExportExcel.disabled = false;
      btnExportExcel.onclick = () => window.open(data.excel_download_url, "_blank");
    }

    renderAuditIndicatorsTable(indicators);

    const anomaliesList = document.getElementById("anomalies-list");
    if (anomaliesList) {
      anomaliesList.innerHTML = "";
      if (anomalies.length === 0) {
        anomaliesList.innerHTML = '<div class="p-8 text-center text-slate-400 text-xs">未发现跨指标数据冲突。</div>';
      } else {
        anomalies.forEach(a => {
          const borderClass = a.level === "WARNING"
            ? "border-amber-200 bg-amber-50/40 text-amber-900"
            : (a.level === "SUCCESS" ? "border-emerald-200 bg-emerald-50/40 text-emerald-900" : "border-slate-200 bg-slate-50/50 text-slate-800");
          const iconHtml = a.level === "WARNING"
            ? '<i class="ph ph-warning text-amber-600 text-lg"></i>'
            : (a.level === "SUCCESS" ? '<i class="ph ph-check-circle text-emerald-600 text-lg"></i>' : '<i class="ph ph-info text-blue-600 text-lg"></i>');

          const div = document.createElement("div");
          div.className = `p-3.5 rounded-xl border ${borderClass} flex items-start space-x-3`;
          div.innerHTML = `
            <div class="mt-0.5 flex-shrink-0">${iconHtml}</div>
            <div class="flex-1 space-y-1">
              <div class="flex items-center justify-between gap-2">
                <span class="font-bold text-xs">${escapeHtml(a.title)}</span>
                <span class="font-mono text-[11px] px-2 py-0.5 rounded bg-white/80 border border-slate-200 text-slate-500">${escapeHtml(a.code)}</span>
              </div>
              <p class="text-xs text-slate-600 leading-relaxed">${escapeHtml(a.message)}</p>
            </div>
          `;
          anomaliesList.appendChild(div);
        });
      }
    }
  }

  // 管理员一键收录入库
  if (btnAdminPublishReport) {
    btnAdminPublishReport.addEventListener("click", async () => {
      if (!isAdmin) {
        openAdminLoginModal();
        return;
      }
      if (!currentAnalysis || !currentAnalysis.summary) return;

      const token = sessionStorage.getItem("esg_admin_token") || "";
      btnAdminPublishReport.disabled = true;
      btnAdminPublishReport.innerHTML = '<i class="ph ph-spinner animate-spin text-sm"></i><span>正在入库...</span>';

      const customCode = adminPublishCodeInput ? adminPublishCodeInput.value.trim() : "";
      const customIndustry = adminPublishIndustrySelect ? adminPublishIndustrySelect.value : "";

      try {
        const payload = {
          company_name: currentAnalysis.summary.company_name,
          company_code: customCode || currentAnalysis.summary.company_code || null,
          industry_l1: customIndustry || currentAnalysis.summary.industry_l1 || "电子",
          year: currentAnalysis.summary.report_year,
          title: currentAnalysis.summary.report_title,
          total_pages: currentAnalysis.summary.total_pages || 0,
          disclosure_rate: currentAnalysis.summary.disclosure_rate || "0.0%",
          verified_rate: currentAnalysis.summary.verification_rate || "0.0%",
          temp_pdf_id: currentAnalysis.temp_pdf_id || null,
          original_filename: currentAnalysis.original_filename || null,
          indicators: currentAnalysis.indicators || []
        };

        const resp = await fetch("/api/admin/reports/publish", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Admin-Token": token
          },
          body: JSON.stringify(payload)
        });
        const res = await resp.json();

        if (!resp.ok) {
          showToast("发布入库失败：" + (res.detail || "请检查数据或登录状态"), "error");
          btnAdminPublishReport.disabled = false;
          btnAdminPublishReport.innerHTML = '<i class="ph ph-cloud-arrow-up text-sm"></i><span>确认收录入库</span>';
          return;
        }

        currentAnalysis.is_published = true;
        currentAnalysis.published_report_id = res.report_id;
        samplesLoaded = false;

        showToast(
          `已成功收录至报告库\n${res.company_name} (${res.company_code}) · 共 ${res.kpis_inserted} 项指标`,
          "success"
        );

        refreshExtractionBanners();
        loadCompaniesView();
        loadReportsView();
        loadRankingsView();
        loadStats();
      } catch (e) {
        showToast("发布请求异常：" + e.message, "error");
        btnAdminPublishReport.disabled = false;
        btnAdminPublishReport.innerHTML = '<i class="ph ph-cloud-arrow-up text-sm"></i><span>确认收录入库</span>';
      }
    });
  }

  // ==================== 8. 弹窗交互（支持背景点击与 Esc 键关闭） ====================
  const modalEvidence = document.getElementById("modal-evidence");
  const modalClose = document.getElementById("modal-close");
  const modalBtnConfirm = document.getElementById("modal-btn-confirm");
  const modalTitle = document.getElementById("modal-title");
  const modalMetricName = document.getElementById("modal-metric-name");
  const modalPageTag = document.getElementById("modal-page-tag");
  const modalQuote = document.getElementById("modal-quote");
  const modalVerifyStatus = document.getElementById("modal-verify-status");

  function showEvidenceModal(item) {
    if (!modalEvidence) return;
    modalTitle.textContent = "原文出处";
    modalMetricName.textContent = item.name || "--";
    modalPageTag.textContent = item.page ? `第 ${item.page} 页` : "页码未标注";
    modalQuote.textContent = item.quote || "暂无原文引用片段";

    if (item.verified_in_page) {
      modalVerifyStatus.className = "flex items-center space-x-2 text-xs font-medium p-2.5 rounded-xl bg-emerald-50 text-emerald-800 border border-emerald-200/80";
      modalVerifyStatus.innerHTML = '<i class="ph ph-check-circle text-base"></i><span>数据与对应页披露原文一致。</span>';
    } else {
      modalVerifyStatus.className = "flex items-center space-x-2 text-xs font-medium p-2.5 rounded-xl bg-amber-50 text-amber-800 border border-amber-200/80";
      modalVerifyStatus.innerHTML = '<i class="ph ph-info text-base"></i><span>请结合原版报告对应页码核对上下文。</span>';
    }
    modalEvidence.classList.remove("hidden");
  }

  function closeEvidenceModal() {
    if (modalEvidence) modalEvidence.classList.add("hidden");
  }

  if (modalClose) modalClose.addEventListener("click", closeEvidenceModal);
  if (modalBtnConfirm) modalBtnConfirm.addEventListener("click", closeEvidenceModal);

  const modalSettings = document.getElementById("modal-settings");
  const settingsClose = document.getElementById("settings-close");
  const settingsBtnCancel = document.getElementById("settings-btn-cancel");
  const settingsBtnSave = document.getElementById("settings-btn-save");
  const cfgProvider = document.getElementById("cfg-provider");
  const cfgApiKey = document.getElementById("cfg-api-key");
  const cfgModel = document.getElementById("cfg-model");
  const cfgBaseUrl = document.getElementById("cfg-base-url");
  const divBaseUrl = document.getElementById("div-base-url");

  function closeSettingsModal() {
    if (modalSettings) modalSettings.classList.add("hidden");
  }

  if (settingsClose) settingsClose.addEventListener("click", closeSettingsModal);
  if (settingsBtnCancel) settingsBtnCancel.addEventListener("click", closeSettingsModal);

  if (cfgProvider) {
    cfgProvider.addEventListener("change", () => {
      const p = cfgProvider.value;
      if (divBaseUrl) divBaseUrl.classList.toggle("hidden", p !== "openai");
      if (serverSettingsCache) {
        updateSettingsModalFields({ ...serverSettingsCache, provider: p });
      }
    });
  }

  if (settingsBtnSave) {
    settingsBtnSave.addEventListener("click", async () => {
      const payload = {
        provider: cfgProvider.value,
        api_key: cfgApiKey.value.trim(),
        model: cfgModel.value.trim() || null,
        base_url: cfgBaseUrl.value.trim() || null
      };

      try {
        const token = sessionStorage.getItem("esg_admin_token") || "";
        const resp = await fetch("/api/settings", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Admin-Token": token
          },
          body: JSON.stringify(payload)
        });
        if (resp.ok) {
          cfgApiKey.value = "";
          await syncAdminSettingsStatus();
          closeSettingsModal();
          showToast("全局模型配置已保存生效", "success");
        } else {
          const d = await resp.json();
          showToast("保存失败：" + (d.detail || "请检查参数或登录状态"), "error");
        }
      } catch (e) {
        showToast("请求异常：" + e.message, "error");
      }
    });
  }

  // 点击遮罩层或按 Esc 关闭弹窗
  [modalEvidence, modalSettings, modalAdminLogin].forEach(modal => {
    if (!modal) return;
    modal.addEventListener("click", (e) => {
      if (e.target === modal) {
        if (modal === modalAdminLogin) closeAdminLoginModal();
        else modal.classList.add("hidden");
      }
    });
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeEvidenceModal();
      closeSettingsModal();
      closeAdminLoginModal();
    }
  });

  function loadStats() {
    fetch("/api/stats")
      .then(r => r.json())
      .then(d => {
        const elComp = document.getElementById("stat-companies");
        if (elComp) elComp.textContent = Number(d.total_companies).toLocaleString();
        const elRep = document.getElementById("stat-reports");
        if (elRep) elRep.textContent = Number(d.total_reports).toLocaleString();
        const elKpi = document.getElementById("stat-kpis");
        if (elKpi) elKpi.textContent = Number(d.total_kpis).toLocaleString();
      });
  }

  updateAdminUI();
  switchView("view-home");
});
