"""
Sidebar navigation utilities for role-based menu visibility.
"""

import streamlit as st
from auth.login import is_authenticated
from auth.session import get_current_role


def hide_unauthorized_pages():
    """Hide unauthorized pages from sidebar based on current user role.
    
    Shows only allowed pages as a list in the sidebar menu.
    """
    if not is_authenticated():
        return
    
    current_role = get_current_role()
    if not current_role:
        return
    
    # Define which pages each role can access (hardcoded for demo)
    # Manager: Manager, Manager Training, Manager Predictive, Technician
    # Technician: Technician, Technician Map, Run
    # Engineer: Engineer, Engineer Requests
    
    # Map page identifiers to their file patterns
    page_file_map = {
        "engineer": ["3_Engineer", "Engineer"],
        "engineer_requests": ["3_Engineer_Requests", "Engineer Requests"],
        "manager": ["2_Manager", "Manager"],
        "manager_training": ["2_Manager_Training", "Manager Training"],
        "manager_predictive": ["2_Manager_Predictive", "Manager Predictive"],
        "technician": ["1_Technician", "Technician"],
        "technician_map": ["2_Technician_Map", "Technician Map"],
        "run": ["4_Run", "Run"],
        "login": ["0_login", "login"],
        "home": ["0_Home", "Home"]
    }
    
    # Pages to hide based on role (hardcoded for demo)
    if current_role == "manager":
        # Manager can see: Manager (home), Manager Training, Manager Predictive, Technician
        # Hide: Engineer, Engineer Requests, Technician Map, Run, Login, Home
        pages_to_hide = ["engineer", "engineer_requests", "technician_map", "run", "login", "home"]
    elif current_role == "technician":
        # Technician can see: Technician (home), Technician Map, Run
        # Hide: Manager, Manager Training, Manager Predictive, Engineer, Engineer Requests, Login, Home
        pages_to_hide = ["manager", "manager_training", "manager_predictive", "engineer", "engineer_requests", "login", "home"]
    elif current_role == "engineer":
        # Engineer can see: Engineer (home), Engineer Requests
        # Hide: Manager, Manager Training, Manager Predictive, Technician, Technician Map, Run, Login, Home
        pages_to_hide = ["manager", "manager_training", "manager_predictive", "technician", "technician_map", "run", "login", "home"]
    else:
        pages_to_hide = ["login"]
    
    # Build CSS to hide unauthorized pages
    css = """
    <style>
    """
    
    for page in pages_to_hide:
        # Multiple CSS selectors to catch different Streamlit sidebar structures
        # Try various patterns to match page names
        page_patterns = [
            page.lower(),
            page.replace("_", " ").lower(),
            page.replace("_", "-").lower(),
        ]
        
        for pattern in page_patterns:
            css += f"""
            /* Hide {page} */
            div[data-testid="stSidebarNav"] a[href*="{pattern}"] {{
                display: none !important;
            }}
            div[data-testid="stSidebarNav"] li:has(a[href*="{pattern}"]) {{
                display: none !important;
            }}
            div[data-testid="stSidebarNav"] a[href*="{page}"] {{
                display: none !important;
            }}
            div[data-testid="stSidebarNav"] li:has(a[href*="{page}"]) {{
                display: none !important;
            }}
            """
        
        # Also try matching by exact page filename patterns
        if page in page_file_map:
            for filename in page_file_map[page]:
                css += f"""
            div[data-testid="stSidebarNav"] a[href*="{filename}"] {{
                display: none !important;
            }}
            div[data-testid="stSidebarNav"] li:has(a[href*="{filename}"]) {{
                display: none !important;
            }}
            div[data-testid="stSidebarNav"] a[href*="{filename.lower()}"] {{
                display: none !important;
            }}
            div[data-testid="stSidebarNav"] li:has(a[href*="{filename.lower()}"]) {{
                display: none !important;
            }}
            """
    
    css += """
    </style>
    """
    
    st.markdown(css, unsafe_allow_html=True)
    
    # Also use JavaScript to remove restricted pages (more reliable)
    # Convert pages_to_hide to JavaScript array format
    js_pages = '["' + '", "'.join(pages_to_hide) + '"]'
    
    # Convert page_file_map to JavaScript format
    js_page_map_parts = []
    for key, values in page_file_map.items():
        values_str = '[' + ', '.join([f"'{v}'" for v in values]) + ']'
        js_page_map_parts.append(f"'{key}': {values_str}")
    js_page_map = "{" + ", ".join(js_page_map_parts) + "}"
    
    # Map page file patterns to their display names for sidebar
    page_display_names = {
        "2_Manager": "Manager Dashboard",
        "Manager": "Manager Dashboard",
        "manager": "Manager Dashboard",
        "3_Engineer": "Engineer Dashboard",
        "Engineer": "Engineer Dashboard",
        "engineer": "Engineer Dashboard",
        "1_Technician": "Technician Dashboard",
        "Technician": "Technician Dashboard",
        "technician": "Technician Dashboard",
        "4_Run": "Ticket Update",
        "Run": "Ticket Update",
        "run": "Ticket Update",
        "Workstation": "Ticket Update",
        "2_Technician_Map": "Action Plan",
        "Technician Map": "Action Plan",
        "technician map": "Action Plan",
        "Floor Map": "Action Plan",
        "2_Manager_Predictive": "Predictive Maintenance Agent",
        "Manager Predictive": "Predictive Maintenance Agent",
        "manager predictive": "Predictive Maintenance Agent",
        "Predictive Maintenance": "Predictive Maintenance Agent",
        "2_Manager_Training": "Technician Training",
        "Manager Training": "Technician Training",
        "manager training": "Technician Training",
        "Tech Training": "Technician Training",
        "3_Engineer_Requests": "Ticket Request",
        "Engineer Requests": "Ticket Request",
        "engineer requests": "Ticket Request",
        "My Requests": "Ticket Request",
    }
    
    js_display_names = "{"
    for key, value in page_display_names.items():
        js_display_names += f"'{key}': '{value}', "
    js_display_names = js_display_names.rstrip(", ") + "}"
    
    js = f"""
    <script>
    (function() {{
        function hideRestrictedPages() {{
            const restrictedPages = {js_pages};
            const pageFileMap = {js_page_map};
            
            // Get all navigation links and list items
            const navContainer = document.querySelector('[data-testid="stSidebarNav"]');
            if (!navContainer) return;
            
            // Get all list items in the navigation
            const navItems = navContainer.querySelectorAll('li, a');
            
            navItems.forEach(function(element) {{
                const href = element.getAttribute('href') || '';
                const text = (element.textContent || '').toLowerCase().trim();
                
                // Check each restricted page
                restrictedPages.forEach(function(page) {{
                    const patterns = pageFileMap[page] || [page];
                    patterns.forEach(function(pattern) {{
                        const patternLower = pattern.toLowerCase();
                        // Check if this element matches a restricted page
                        if (href.includes(pattern) || href.includes(patternLower) || 
                            text.includes(patternLower) || text.includes(page.replace('_', ' '))) {{
                            // Hide the element and walk up to hide parent list items
                            element.style.display = 'none';
                            let parent = element.parentElement;
                            while (parent && parent !== navContainer) {{
                                if (parent.tagName === 'LI') {{
                                    parent.style.display = 'none';
                                }}
                                parent = parent.parentElement;
                            }}
                        }}
                    }});
                }});
            }});
        }}
        
        function renamePageNames() {{
            const pageDisplayNames = {js_display_names};
            const navContainer = document.querySelector('[data-testid="stSidebarNav"]');
            if (!navContainer) return;
            
            // Get all navigation links
            const navLinks = navContainer.querySelectorAll('a[href*="pages/"]');
            
            navLinks.forEach(function(link) {{
                const href = link.getAttribute('href') || '';
                const currentText = (link.textContent || '').trim();
                
                // Extract page filename from href (e.g., "pages/2_Manager" -> "2_Manager")
                const hrefMatch = href.match(/pages\/([^/?]+)/);
                const pageFileName = hrefMatch ? hrefMatch[1] : '';
                
                // Check each page pattern and rename if matched
                for (const [pattern, displayName] of Object.entries(pageDisplayNames)) {{
                    const patternLower = pattern.toLowerCase();
                    const hrefLower = href.toLowerCase();
                    const textLower = currentText.toLowerCase();
                    const fileNameLower = pageFileName.toLowerCase();
                    
                    // Match by filename, href, or displayed text
                    if (fileNameLower.includes(patternLower) || 
                        hrefLower.includes(patternLower) || 
                        textLower === patternLower ||
                        textLower.includes(patternLower)) {{
                        // Only rename if it's different
                        if (currentText !== displayName) {{
                            // Update the link text
                            if (link.childNodes.length === 1 && link.childNodes[0].nodeType === Node.TEXT_NODE) {{
                                link.childNodes[0].textContent = displayName;
                            }} else {{
                                link.textContent = displayName;
                            }}
                            // Also update any parent elements that might contain the text
                            let parent = link.parentElement;
                            while (parent && parent !== navContainer) {{
                                if (parent.textContent && parent.textContent.trim() === currentText) {{
                                    // Update text content while preserving structure
                                    const children = Array.from(parent.childNodes);
                                    children.forEach(function(child) {{
                                        if (child.nodeType === Node.TEXT_NODE && child.textContent.trim() === currentText) {{
                                            child.textContent = displayName;
                                        }}
                                    }});
                                }}
                                parent = parent.parentElement;
                            }}
                        }}
                        break;
                    }}
                }}
            }});
        }}
        
        function runBoth() {{
            hideRestrictedPages();
            renamePageNames();
        }}
        
        // Run immediately and also after delays to catch dynamic content
        runBoth();
        setTimeout(runBoth, 100);
        setTimeout(runBoth, 300);
        setTimeout(runBoth, 500);
        setTimeout(runBoth, 1000);
        
        // Also watch for navigation changes
        const observer = new MutationObserver(runBoth);
        const navContainer = document.querySelector('[data-testid="stSidebarNav"]');
        if (navContainer) {{
            observer.observe(navContainer, {{ childList: true, subtree: true }});
        }}
    }})();
    </script>
    """
    st.markdown(js, unsafe_allow_html=True)

