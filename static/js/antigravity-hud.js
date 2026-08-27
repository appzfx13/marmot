/**
 * ====================================================================
 * GOOGLE ANTIGRAVITY & FUTURISTIC HUD CONTROLLER
 * Handles Theme Toggling, Cmd+K Spotlight HUD, Clipboard & HTMX Sync
 * ====================================================================
 */

(function() {
  'use strict';

  // --- 1. Zero-FOUC Theme Management ---
  function getPreferredTheme() {
    const savedTheme = localStorage.getItem('marmot_theme') || localStorage.getItem('ag_theme');
    if (savedTheme) {
      return savedTheme;
    }
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    localStorage.setItem('marmot_theme', theme);
    localStorage.setItem('ag_theme', theme);
    updateThemeToggleIcons(theme);
  }

  function updateThemeToggleIcons(theme) {
    const sunIcons = document.querySelectorAll('.theme-icon-sun');
    const moonIcons = document.querySelectorAll('.theme-icon-moon');
    
    sunIcons.forEach(icon => {
      icon.style.display = theme === 'dark' ? 'inline-block' : 'none';
    });
    moonIcons.forEach(icon => {
      icon.style.display = theme === 'dark' ? 'none' : 'inline-block';
    });
  }

  window.toggleTheme = function() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    applyTheme(newTheme);
  };

  // Immediate execution on script load
  const initialTheme = getPreferredTheme();
  applyTheme(initialTheme);

  // --- 2. Spotlight Command Palette HUD (Cmd+K / Ctrl+K) ---
  window.toggleCommandPalette = function(forceState) {
    const backdrop = document.getElementById('ag-cmd-palette');
    const input = document.getElementById('ag-cmd-input');
    if (!backdrop) return;

    const isActive = forceState !== undefined ? forceState : !backdrop.classList.contains('active');
    backdrop.classList.toggle('active', isActive);

    if (isActive && input) {
      setTimeout(() => input.focus(), 50);
    }
  };

  document.addEventListener('keydown', function(e) {
    // Open/Close on Cmd+K or Ctrl+K
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      window.toggleCommandPalette();
    }
    // Close on Escape
    if (e.key === 'Escape') {
      const backdrop = document.getElementById('ag-cmd-palette');
      if (backdrop && backdrop.classList.contains('active')) {
        window.toggleCommandPalette(false);
      }
    }
  });

  // Client-side quick filter for command palette items
  window.filterCommandPalette = function(input) {
    const query = input.value.toLowerCase().trim();
    const items = document.querySelectorAll('.ag-cmd-item');
    const groups = document.querySelectorAll('.ag-cmd-group');

    items.forEach(item => {
      const text = item.textContent.toLowerCase();
      const match = text.includes(query);
      item.style.display = match ? 'flex' : 'none';
    });

    groups.forEach(group => {
      const visibleChildren = group.querySelectorAll('.ag-cmd-item:not([style*="display: none"])');
      group.style.display = visibleChildren.length > 0 ? 'block' : 'none';
    });
  };

  // --- 3. Clipboard Copy Helper for Code Blocks ---
  window.copyCodeSnippet = function(btn) {
    const codeBlock = btn.closest('.ag-code-block') || btn.closest('.code-block');
    if (!codeBlock) return;

    const pre = codeBlock.querySelector('pre code') || codeBlock.querySelector('pre');
    if (!pre) return;

    const codeText = pre.innerText;
    navigator.clipboard.writeText(codeText).then(() => {
      const originalHtml = btn.innerHTML;
      btn.innerHTML = '<span style="color: var(--success, #10b981);">✓ Copied</span>';
      setTimeout(() => {
        btn.innerHTML = originalHtml;
      }, 2000);
    }).catch(err => {
      console.warn('Failed to copy code snippet:', err);
    });
  };

  // --- 4. HTMX View Transitions & Progress Bar Integration ---
  document.addEventListener('DOMContentLoaded', function() {
    // Sync theme icons once DOM is ready
    updateThemeToggleIcons(document.documentElement.getAttribute('data-theme') || 'dark');

    // Enable HTMX Global View Transitions if supported
    if (window.htmx && window.htmx.config) {
      window.htmx.config.globalViewTransitions = true;
    }
  });

  // Listen to HTMX afterSwap to re-attach or re-evaluate dynamic components
  document.addEventListener('htmx:afterSwap', function() {
    updateThemeToggleIcons(document.documentElement.getAttribute('data-theme') || 'dark');
  });

  // --- 5. Global Mobile & Portrait Mode Drawer Controller ---
  window.isPortraitOrMobile = function() {
    return window.innerWidth < 992 || (window.matchMedia && window.matchMedia('(orientation: portrait)').matches);
  };

  window.closeGlobalSidebar = function() {
    const sidebar = document.getElementById('mainSidebar') || document.querySelector('.sidebar');
    const overlay = document.getElementById('sidebarOverlay') || document.querySelector('.sidebar-overlay');
    if (sidebar) sidebar.classList.remove('show');
    if (overlay) overlay.classList.remove('show');
    document.body.classList.remove('sidebar-mobile-open');
  };

  // Auto-close drawer on HTMX navigation in portrait/mobile mode
  document.addEventListener('htmx:pushedIntoHistory', function() {
    if (window.isPortraitOrMobile()) {
      window.closeGlobalSidebar();
    }
  });

  // Auto-close on orientation change to desktop landscape
  if (window.matchMedia) {
    try {
      window.matchMedia('(orientation: portrait)').addEventListener('change', function(e) {
        if (!e.matches && window.innerWidth >= 992) {
          window.closeGlobalSidebar();
        }
      });
    } catch (err) {}
  }

})();
