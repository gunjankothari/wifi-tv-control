import AsyncStorage from '@react-native-async-storage/async-storage';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { WebView } from 'react-native-webview';
import { DEFAULT_PORT, helperUrl } from './address';

const STORAGE_KEY = 'tvremote.helperAddress';
const UNREACHABLE =
  "Couldn't reach the helper. Check that TV Remote is running on the computer, that " +
  '"Phone access" is switched on, and that this device is on the same Wi-Fi.';

/** Web only: true when something answers at the URL. The reply is opaque (no CORS), which is all we need. */
async function reachable(url: string): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 5000);
  try {
    await fetch(url, { mode: 'no-cors', signal: controller.signal });
    return true;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

export default function App() {
  const [loaded, setLoaded] = useState(false);
  const [input, setInput] = useState('');
  const [url, setUrl] = useState<string | null>(null); // the remote being shown (native) or opened (web)
  const [error, setError] = useState<string | null>(null);
  const [failed, setFailed] = useState(false); // the WebView couldn't load the page
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY)
      .catch(() => null)
      .then((saved) => {
        if (saved) {
          setInput(saved);
          // The native app goes straight to the remote. On the web the remote replaces this page,
          // so we wait for a tap; otherwise there would be no way back to change the address.
          if (Platform.OS !== 'web') setUrl(helperUrl(saved));
        }
        setLoaded(true);
      });
  }, []);

  async function connect() {
    const target = helperUrl(input);
    if (!target) {
      setError(`Enter the address shown in TV Remote under "Phone access", for example 192.168.1.20:${DEFAULT_PORT}.`);
      return;
    }
    setError(null);
    await AsyncStorage.setItem(STORAGE_KEY, input.trim()).catch(() => undefined);
    if (Platform.OS !== 'web') {
      setFailed(false);
      setUrl(target);
      return;
    }
    // The helper's sign-in cookie is SameSite=Strict, so the page can't live in an iframe: open it directly.
    setBusy(true);
    const ok = await reachable(target);
    setBusy(false);
    if (ok) window.location.assign(target);
    else setError(UNREACHABLE);
  }

  function changeAddress() {
    setUrl(null);
    setFailed(false);
    setError(null);
  }

  let body;
  if (!loaded) {
    body = <ActivityIndicator color={colors.accent} style={styles.center} />;
  } else if (url && Platform.OS !== 'web') {
    body = (
      <View style={styles.fill}>
        <View style={styles.bar}>
          <Text style={styles.barText} numberOfLines={1}>
            {url.replace(/^https?:\/\/|\/$/g, '')}
          </Text>
          <Pressable onPress={changeAddress} hitSlop={10} accessibilityRole="button">
            <Text style={styles.link}>Change</Text>
          </Pressable>
        </View>
        {failed ? (
          <View style={styles.form}>
            <Text style={styles.title}>Can't connect</Text>
            <Text style={styles.error}>{UNREACHABLE}</Text>
            <Pressable style={styles.button} onPress={() => setFailed(false)} accessibilityRole="button">
              <Text style={styles.buttonText}>Try again</Text>
            </Pressable>
            <Pressable style={styles.secondary} onPress={changeAddress} accessibilityRole="button">
              <Text style={styles.link}>Change address</Text>
            </Pressable>
          </View>
        ) : (
          <WebView
            source={{ uri: url }}
            style={styles.web}
            onError={() => setFailed(true)}
            startInLoadingState
            renderLoading={() => <ActivityIndicator color={colors.accent} style={styles.loading} />}
            // Only the helper's own page stays in the app.
            originWhitelist={[url.replace(/\/$/, '') + '*']}
            sharedCookiesEnabled
            pullToRefreshEnabled
          />
        )}
      </View>
    );
  } else {
    body = (
      <KeyboardAvoidingView style={styles.form} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <Text style={styles.title}>TV Remote</Text>
        <Text style={styles.hint}>
          Enter the address shown in TV Remote on your computer under "Phone access". The PIN is asked on the next
          screen.
        </Text>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          onSubmitEditing={connect}
          placeholder={`192.168.1.20:${DEFAULT_PORT}`}
          placeholderTextColor={colors.muted}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          returnKeyType="go"
          accessibilityLabel="Helper address"
        />
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <Pressable style={[styles.button, busy && styles.busy]} onPress={connect} disabled={busy} accessibilityRole="button">
          <Text style={styles.buttonText}>{busy ? 'Connecting…' : error === UNREACHABLE ? 'Try again' : 'Connect'}</Text>
        </Pressable>
      </KeyboardAvoidingView>
    );
  }

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.fill}>
        <StatusBar style="light" />
        {body}
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

// Same palette as the phone web UI (helper/web/index.html): dark navy surfaces, indigo accent.
const colors = {
  bg: '#0b1020',
  surface: '#151b33',
  border: '#2a3157',
  text: '#eef0ff',
  muted: '#8f97c2',
  accent: '#6366f1',
  danger: '#ff8a8a',
};

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  center: { flex: 1 },
  loading: { position: 'absolute', top: 0, bottom: 0, left: 0, right: 0, backgroundColor: colors.bg },
  web: { flex: 1, backgroundColor: colors.bg },
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  barText: { color: colors.muted, fontSize: 13, flexShrink: 1, marginRight: 12 },
  link: { color: colors.accent, fontSize: 15, fontWeight: '600' },
  form: { flex: 1, justifyContent: 'center', padding: 24, width: '100%', maxWidth: 480, alignSelf: 'center' },
  title: { color: colors.text, fontSize: 28, fontWeight: '700', marginBottom: 8 },
  hint: { color: colors.muted, fontSize: 15, lineHeight: 21, marginBottom: 20 },
  input: {
    color: colors.text,
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 17,
    marginBottom: 12,
  },
  error: { color: colors.danger, fontSize: 14, lineHeight: 20, marginBottom: 12 },
  button: { backgroundColor: colors.accent, borderRadius: 12, paddingVertical: 14, alignItems: 'center' },
  busy: { opacity: 0.6 },
  buttonText: { color: '#fff', fontSize: 17, fontWeight: '600' },
  secondary: { alignItems: 'center', paddingVertical: 16 },
});
