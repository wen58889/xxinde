import { Box, Typography, TextField, Button, Paper, Divider, Snackbar, Alert, CircularProgress, InputAdornment, IconButton as MuiIconButton, Chip, Select, MenuItem } from '@mui/material'
import VisibilityIcon from '@mui/icons-material/Visibility'
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff'
import BiotechIcon from '@mui/icons-material/Biotech'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import CancelIcon from '@mui/icons-material/Cancel'
import { useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { useLogStore } from '../stores/logStore'
import { colors } from '../theme'
import client from '../api/client'

const STORAGE_KEY = 'phone_test_settings'

export default function Settings() {
  const addLog = useLogStore((s) => s.addLog)
  const nav = useNavigate()
  const [serverIp, setServerIp] = useState('192.168.5.8')
  const [visionPort, setVisionPort] = useState('8000')
  const [apiPort, setApiPort] = useState('8080')
  const [moonrakerPort, setMoonrakerPort] = useState('7125')
  const [go2rtcPort, setGo2rtcPort] = useState('1984')
  const [openaiKey, setOpenaiKey] = useState('')
  const [anthropicKey, setAnthropicKey] = useState('')
  const [vllmBaseUrl, setVllmBaseUrl] = useState('http://192.168.5.8:8000')
  const [customApiBaseUrl, setCustomApiBaseUrl] = useState('')
  const [customApiKey, setCustomApiKey] = useState('')
  const [customApiModel, setCustomApiModel] = useState('')
  const [ttsSecretId, setTtsSecretId] = useState('')
  const [ttsSecretKey, setTtsSecretKey] = useState('')
  const [ttsVoiceType, setTtsVoiceType] = useState(1001)
  const [ttsEngine, setTtsEngine] = useState('tencent')
  const [ttsCustomUrl, setTtsCustomUrl] = useState('')
  const [ttsCustomKey, setTtsCustomKey] = useState('')
  const [modelscopeToken, setModelscopeToken] = useState('')
  const [showKeys, setShowKeys] = useState(false)
  const [saving, setSaving] = useState(false)
  const [snack, setSnack] = useState<{ open: boolean; msg: string; severity: 'success' | 'error' }>({ open: false, msg: '', severity: 'success' })
  // Status loaded from backend (whether keys are configured)
  const [apiStatus, setApiStatus] = useState<{ openai: boolean; anthropic: boolean; custom: boolean; modelscope: boolean; vllm_url: string; tts: boolean }>({
    openai: false, anthropic: false, custom: false, modelscope: false, vllm_url: '', tts: false,
  })

  const refreshApiStatus = () => {
    client.get<{ vllm_base_url: string; custom_api_base_url: string; custom_api_model: string; openai_configured: boolean; anthropic_configured: boolean; custom_configured: boolean }>('/settings/vision')
      .then(r => {
        if (r.data.custom_api_base_url) setCustomApiBaseUrl(r.data.custom_api_base_url)
        if (r.data.custom_api_model) setCustomApiModel(r.data.custom_api_model)
        if (r.data.vllm_base_url) setVllmBaseUrl(r.data.vllm_base_url)
        setApiStatus({
          openai: r.data.openai_configured,
          anthropic: r.data.anthropic_configured,
          custom: r.data.custom_configured,
          modelscope: (r.data as any).modelscope_configured ?? false,
          vllm_url: r.data.vllm_base_url,
          tts: (r.data as any).tts_configured ?? false,
        })
      })
      .catch(() => { /* backend may not be running */ })
  }

  // Load from localStorage on mount, then sync actual API-key state from backend
  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      try {
        const s = JSON.parse(saved)
        if (s.serverIp) setServerIp(s.serverIp)
        if (s.visionPort) setVisionPort(s.visionPort)
        if (s.apiPort) setApiPort(s.apiPort)
        if (s.moonrakerPort) setMoonrakerPort(s.moonrakerPort)
        if (s.go2rtcPort) setGo2rtcPort(s.go2rtcPort)
        if (s.openaiKey) setOpenaiKey(s.openaiKey)
        if (s.anthropicKey) setAnthropicKey(s.anthropicKey)
        if (s.vllmBaseUrl) setVllmBaseUrl(s.vllmBaseUrl)
        if (s.modelscopeToken) setModelscopeToken(s.modelscopeToken)
        if (s.customApiBaseUrl) setCustomApiBaseUrl(s.customApiBaseUrl)
        if (s.customApiKey) setCustomApiKey(s.customApiKey)
        if (s.customApiModel) setCustomApiModel(s.customApiModel)
        if (s.ttsSecretId) setTtsSecretId(s.ttsSecretId)
        if (s.ttsSecretKey) setTtsSecretKey(s.ttsSecretKey)
        if (s.ttsVoiceType) setTtsVoiceType(s.ttsVoiceType)
        if (s.ttsEngine) setTtsEngine(s.ttsEngine)
        if (s.ttsCustomUrl) setTtsCustomUrl(s.ttsCustomUrl)
        if (s.ttsCustomKey) setTtsCustomKey(s.ttsCustomKey)
      } catch { /* ignore */ }
    }
    refreshApiStatus()
  }, [])

  const handleSave = async () => {
    // Save UI/connection settings to localStorage
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      serverIp, visionPort, apiPort, moonrakerPort, go2rtcPort,
      openaiKey, anthropicKey, vllmBaseUrl,
      modelscopeToken,
      customApiBaseUrl, customApiKey, customApiModel,
      ttsSecretId, ttsSecretKey, ttsVoiceType, ttsEngine, ttsCustomUrl, ttsCustomKey,
    }))
    // Sync API credentials to backend
    setSaving(true)
    try {
      await client.post('/settings/vision', {
        openai_api_key: openaiKey,
        anthropic_api_key: anthropicKey,
        vllm_base_url: vllmBaseUrl,
        modelscope_token: modelscopeToken,
        custom_api_base_url: customApiBaseUrl,
        custom_api_key: customApiKey,
        custom_api_model: customApiModel,
        tts_secret_id: ttsSecretId,
        tts_secret_key: ttsSecretKey,
        tts_voice_type: ttsVoiceType,
        tts_engine: ttsEngine,
        tts_custom_url: ttsCustomUrl,
        tts_custom_key: ttsCustomKey,
      })
      setSnack({ open: true, msg: '配置已保存', severity: 'success' })
      addLog('配置已保存', 'success')
      refreshApiStatus()
    } catch {
      setSnack({ open: true, msg: '保存失败，请检查后端是否在线', severity: 'error' })
      addLog('配置保存失败', 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleReset = () => {
    localStorage.removeItem(STORAGE_KEY)
    setServerIp('192.168.5.8')
    setVisionPort('8000')
    setApiPort('8080')
    setMoonrakerPort('7125')
    setGo2rtcPort('1984')
    setOpenaiKey('')
    setAnthropicKey('')
    setModelscopeToken('')
    setVllmBaseUrl('http://192.168.5.8:8000')
    setCustomApiBaseUrl('')
    setCustomApiKey('')
    setCustomApiModel('')
    setTtsSecretId('')
    setTtsSecretKey('')
    setTtsVoiceType(1001)
    setTtsEngine('tencent')
    setTtsCustomUrl('')
    setTtsCustomKey('')
    addLog('已重置为默认配置', 'warn')
  }

  return (
    <Box sx={{ p: 3, bgcolor: colors.bg, minHeight: '100vh', maxWidth: 600, mx: 'auto' }}>
      <Typography variant="h5" sx={{ mb: 3 }}>系统设置</Typography>

      <Paper sx={{ p: 3, bgcolor: colors.card }}>
        <Typography variant="subtitle1" sx={{ mb: 2 }}>服务器配置</Typography>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <TextField label="总控服务器 IP" value={serverIp} onChange={(e) => setServerIp(e.target.value)} fullWidth size="small" />
          <TextField label="API 端口" value={apiPort} onChange={(e) => setApiPort(e.target.value)} fullWidth size="small" />
        </Box>

        <Divider sx={{ my: 3 }} />

        <Typography variant="subtitle1" sx={{ mb: 2 }}>视觉模型</Typography>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <TextField label="vLLM 服务地址" value={vllmBaseUrl} onChange={(e) => setVllmBaseUrl(e.target.value)} fullWidth size="small" />
          <TextField label="vLLM 端口" value={visionPort} onChange={(e) => setVisionPort(e.target.value)} fullWidth size="small" />
          <Button
            variant="outlined" size="small" startIcon={<BiotechIcon />}
            onClick={() => nav('/vision-test')}
            sx={{ alignSelf: 'flex-start' }}
          >
            视觉模型部署测试
          </Button>
        </Box>

        <Divider sx={{ my: 3 }} />

        <Typography variant="subtitle1" sx={{ mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
          API 密钥（云端推理兜底）
          <MuiIconButton size="small" onClick={() => setShowKeys(v => !v)}>
            {showKeys ? <VisibilityOffIcon fontSize="small" /> : <VisibilityIcon fontSize="small" />}
          </MuiIconButton>
        </Typography>
        <Typography variant="body2" sx={{ mb: 2, color: colors.danger, fontWeight: 500 }}>
          ⚠ 当本地 Ollama/vLLM 识别失败时，自动调用以下 API。填写任意一个即可获得可靠兜底。
        </Typography>
        {/* Current status chips */}
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 2 }}>
          <Chip
            size="small"
            icon={apiStatus.modelscope ? <CheckCircleIcon /> : <CancelIcon />}
            label="ModelScope GUI-Owl"
            color={apiStatus.modelscope ? 'success' : 'default'}
            variant={apiStatus.modelscope ? 'filled' : 'outlined'}
          />
          <Chip
            size="small"
            icon={apiStatus.openai ? <CheckCircleIcon /> : <CancelIcon />}
            label="OpenAI"
            color={apiStatus.openai ? 'success' : 'default'}
            variant={apiStatus.openai ? 'filled' : 'outlined'}
          />
          <Chip
            size="small"
            icon={apiStatus.anthropic ? <CheckCircleIcon /> : <CancelIcon />}
            label="Anthropic"
            color={apiStatus.anthropic ? 'success' : 'default'}
            variant={apiStatus.anthropic ? 'filled' : 'outlined'}
          />
          <Chip
            size="small"
            icon={apiStatus.custom ? <CheckCircleIcon /> : <CancelIcon />}
            label="自定义 API"
            color={apiStatus.custom ? 'success' : 'default'}
            variant={apiStatus.custom ? 'filled' : 'outlined'}
          />
        </Box>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <TextField
            label="OpenAI API Key"
            value={openaiKey}
            onChange={(e) => setOpenaiKey(e.target.value)}
            fullWidth size="small"
            type={showKeys ? 'text' : 'password'}
            placeholder="sk-..."
            slotProps={{
              input: {
                endAdornment: (
                  <InputAdornment position="end">
                    <MuiIconButton size="small" onClick={() => setShowKeys(v => !v)}>
                      {showKeys ? <VisibilityOffIcon fontSize="small" /> : <VisibilityIcon fontSize="small" />}
                    </MuiIconButton>
                  </InputAdornment>
                )
              }
            }}
          />
          <TextField
            label="Anthropic API Key"
            value={anthropicKey}
            onChange={(e) => setAnthropicKey(e.target.value)}
            fullWidth size="small"
            type={showKeys ? 'text' : 'password'}
            placeholder="sk-ant-..."
          />
          <TextField
            label="ModelScope Token（GUI-Owl-1.5 云端推理，免费）"
            value={modelscopeToken}
            onChange={(e) => setModelscopeToken(e.target.value)}
            fullWidth size="small"
            type={showKeys ? 'text' : 'password'}
            placeholder="获取: modelscope.cn → 个人信息 → 访问令牌"
            helperText="填写后自动作为 vLLM 离线时的备份，与本地同款 GUI-Owl-1.5-8B 模型"
          />
        </Box>

        <Divider sx={{ my: 3 }} />

        <Typography variant="subtitle1" sx={{ mb: 1 }}>自定义 OpenAI 兼容 API</Typography>
        <Typography variant="body2" sx={{ mb: 2, color: 'text.secondary' }}>
          支持任意兼容 /chat/completions 的服务：MiniMax、Groq、Together、本地 vLLM 等
        </Typography>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <TextField
            label="Base URL"
            value={customApiBaseUrl}
            onChange={(e) => setCustomApiBaseUrl(e.target.value)}
            fullWidth size="small"
            placeholder="https://api.minimax.chat/v1"
          />
          <TextField
            label="API Key"
            value={customApiKey}
            onChange={(e) => setCustomApiKey(e.target.value)}
            fullWidth size="small"
            type={showKeys ? 'text' : 'password'}
            placeholder="your-api-key"
          />
          <TextField
            label="模型名称"
            value={customApiModel}
            onChange={(e) => setCustomApiModel(e.target.value)}
            fullWidth size="small"
            placeholder="MiniMax-M2.7"
          />
        </Box>

        <Divider sx={{ my: 3 }} />

        <Typography variant="subtitle1" sx={{ mb: 1 }}>TTS 语音合成</Typography>
        <Typography variant="body2" sx={{ mb: 2, color: 'text.secondary' }}>
          Edge TTS 免费免配置；也支持腾讯云、阿里云、微软 Azure、自定义局域网TTS
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 2 }}>
          <Chip
            size="small"
            icon={ttsEngine === 'edge' ? <CheckCircleIcon /> : apiStatus.tts ? <CheckCircleIcon /> : <CancelIcon />}
            label={`TTS (${ttsEngine === 'edge' ? 'Edge免费' : ttsEngine === 'tencent' ? '腾讯云' : ttsEngine === 'aliyun' ? '阿里云' : ttsEngine === 'microsoft' ? '微软' : '自定义'})`}
            color={ttsEngine === 'edge' || apiStatus.tts ? 'success' : 'default'}
            variant={ttsEngine === 'edge' || apiStatus.tts ? 'filled' : 'outlined'}
          />
        </Box>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Select
            value={ttsEngine}
            onChange={(e) => setTtsEngine(e.target.value)}
            size="small"
            fullWidth
          >
            <MenuItem value="edge">Edge TTS（免费免配置）</MenuItem>
            <MenuItem value="tencent">腾讯云 TTS</MenuItem>
            <MenuItem value="aliyun">阿里云 TTS</MenuItem>
            <MenuItem value="microsoft">微软 Azure TTS</MenuItem>
            <MenuItem value="custom">自定义 TTS 服务器（局域网）</MenuItem>
          </Select>

          {ttsEngine === 'edge' ? null : ttsEngine === 'custom' ? (
            <>
              <TextField
                label="TTS 服务器 URL"
                value={ttsCustomUrl}
                onChange={(e) => setTtsCustomUrl(e.target.value)}
                fullWidth size="small"
                placeholder="http://192.168.5.10:9880"
                helperText="需兼容 /synthesize 接口，接收 {text, voice_type} 返回音频"
              />
              <TextField
                label="认证 Key（可选）"
                value={ttsCustomKey}
                onChange={(e) => setTtsCustomKey(e.target.value)}
                fullWidth size="small"
                type={showKeys ? 'text' : 'password'}
                placeholder="Bearer Token"
              />
            </>
          ) : (
            <>
              <TextField
                label={ttsEngine === 'microsoft' ? 'API Key' : 'SecretId / AccessKeyId'}
                value={ttsSecretId}
                onChange={(e) => setTtsSecretId(e.target.value)}
                fullWidth size="small"
                type={showKeys ? 'text' : 'password'}
                placeholder={ttsEngine === 'microsoft' ? 'azure-api-key' : ttsEngine === 'aliyun' ? 'LTAI...' : 'AKID...'}
              />
              <TextField
                label={ttsEngine === 'microsoft' ? 'Region' : ttsEngine === 'aliyun' ? 'AccessKeySecret' : 'SecretKey'}
                value={ttsSecretKey}
                onChange={(e) => setTtsSecretKey(e.target.value)}
                fullWidth size="small"
                type={showKeys ? 'text' : 'password'}
                placeholder={ttsEngine === 'microsoft' ? 'eastasia' : ttsEngine === 'aliyun' ? 'pOgh...' : 'pOgh...'}
              />
            </>
          )}

          <TextField
            label="音色编号"
            value={ttsVoiceType}
            onChange={(e) => setTtsVoiceType(Number(e.target.value))}
            fullWidth size="small"
            type="number"
            helperText={
              ttsEngine === 'edge' ? '1001=Xiaoxiao(女) 1002=Yunxi(男) 1003=Yunyang(男) 1004=Xiaoyi(女)' :
              ttsEngine === 'tencent' ? '1001=智瑜(女) 1002=智聆(男) 1003=智诚(男)' :
              ttsEngine === 'aliyun' ? '1001=知燕(女) 1002=知妙(女) 1003=知燕(通用)' :
              ttsEngine === 'microsoft' ? '1001=Xiaoxiao(女) 1002=Yunxi(男) 1003=Yunyang(男)' :
              '自定义服务器音色编号'
            }
          />
        </Box>

        <Divider sx={{ my: 3 }} />

        <Typography variant="subtitle1" sx={{ mb: 2 }}>N1 节点默认端口</Typography>
        <Box sx={{ display: 'flex', gap: 2 }}>
          <TextField label="Moonraker" value={moonrakerPort} onChange={(e) => setMoonrakerPort(e.target.value)} size="small" />
          <TextField label="拍照服务" value={go2rtcPort} onChange={(e) => setGo2rtcPort(e.target.value)} size="small" />
        </Box>

        <Box sx={{ mt: 3, display: 'flex', gap: 1 }}>
          <Button variant="contained" onClick={handleSave} disabled={saving}
            startIcon={saving ? <CircularProgress size={16} color="inherit" /> : undefined}
            sx={{ bgcolor: colors.success }}>
            {saving ? '保存中…' : '保存配置'}
          </Button>
          <Button variant="outlined" onClick={handleReset} sx={{ color: '#aaa', borderColor: '#555' }}>
            重置默认
          </Button>
        </Box>
      </Paper>

      <Snackbar
        open={snack.open}
        autoHideDuration={3000}
        onClose={() => setSnack(prev => ({ ...prev, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity={snack.severity} onClose={() => setSnack(prev => ({ ...prev, open: false }))}>
          {snack.msg}
        </Alert>
      </Snackbar>
    </Box>
  )
}
