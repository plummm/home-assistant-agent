class HAAgentPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._entities = [];
    this._suggestions = null;
    this._status = "Loading entities...";
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._loaded) {
      this._loaded = true;
      this._loadEntities();
    }
    this._render();
  }

  _render() {
    if (!this.shadowRoot) {
      return;
    }
    const entityCount = this._entities.length;
    const suggestions = this._suggestions
      ? JSON.stringify(this._suggestions, null, 2)
      : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 24px;
          box-sizing: border-box;
          font-family: "IBM Plex Sans", "Fira Sans", "Segoe UI", sans-serif;
          color: var(--primary-text-color);
        }
        .wrap {
          max-width: 900px;
          margin: 0 auto;
          padding: 24px;
          border-radius: 18px;
          background: linear-gradient(135deg, rgba(255, 215, 160, 0.25), rgba(160, 215, 255, 0.2));
          border: 1px solid rgba(0, 0, 0, 0.08);
          box-shadow: 0 12px 30px rgba(0, 0, 0, 0.08);
        }
        h1 {
          font-size: 28px;
          margin: 0 0 8px;
          letter-spacing: 0.4px;
        }
        p {
          margin: 0 0 16px;
          opacity: 0.85;
          line-height: 1.4;
        }
        .row {
          display: flex;
          gap: 12px;
          flex-wrap: wrap;
          align-items: center;
          margin-bottom: 12px;
        }
        input[type="password"] {
          flex: 1;
          min-width: 220px;
          padding: 10px 12px;
          border-radius: 8px;
          border: 1px solid rgba(0, 0, 0, 0.2);
          background: rgba(255, 255, 255, 0.8);
        }
        button {
          padding: 10px 16px;
          border: none;
          border-radius: 8px;
          background: #2f3f5f;
          color: #fdf7e9;
          cursor: pointer;
        }
        button.secondary {
          background: #c96b3f;
        }
        .status {
          font-size: 14px;
          margin-top: 8px;
          opacity: 0.75;
        }
        pre {
          background: rgba(0, 0, 0, 0.08);
          padding: 12px;
          border-radius: 10px;
          overflow: auto;
          max-height: 300px;
        }
        @media (max-width: 600px) {
          :host {
            padding: 16px;
          }
          .wrap {
            padding: 18px;
          }
          h1 {
            font-size: 22px;
          }
        }
      </style>
      <div class="wrap">
        <h1>Home Assistant Agent</h1>
        <p>Placeholder panel for onboarding. Entities discovered: ${entityCount}</p>
        <div class="row">
          <input id="llm-key" type="password" placeholder="Paste LLM API key" />
          <button id="save-key">Save Key</button>
          <button id="run-suggest" class="secondary">Run Suggest</button>
        </div>
        <div class="status">${this._status}</div>
        ${suggestions ? `<pre>${suggestions}</pre>` : ""}
      </div>
    `;

    this.shadowRoot.getElementById("save-key").onclick = () =>
      this._saveKey();
    this.shadowRoot.getElementById("run-suggest").onclick = () =>
      this._runSuggest();
  }

  async _loadEntities() {
    try {
      const data = await this._hass.callApi(
        "GET",
        "home_assistant_agent/entities"
      );
      this._entities = data.entities || [];
      this._status = `Loaded ${this._entities.length} entities.`;
    } catch (err) {
      this._status = `Failed to load entities: ${err}`;
    }
    this._render();
  }

  async _saveKey() {
    const input = this.shadowRoot.getElementById("llm-key");
    const llmKey = input.value || "";
    try {
      await this._hass.callApi("POST", "home_assistant_agent/llm_key", {
        llm_key: llmKey,
      });
      this._status = "LLM key saved.";
    } catch (err) {
      this._status = `Failed to save key: ${err}`;
    }
    this._render();
  }

  async _runSuggest() {
    const input = this.shadowRoot.getElementById("llm-key");
    const llmKey = input.value || "";
    try {
      const result = await this._hass.callApi("POST", "home_assistant_agent/suggest", {
        llm_key: llmKey || undefined,
        use_llm: true,
        entities: this._entities,
      });
      this._suggestions = result;
      this._status = "Suggestions received.";
    } catch (err) {
      this._status = `Suggest failed: ${err}`;
    }
    this._render();
  }
}

customElements.define("home-assistant-agent-panel", HAAgentPanel);
