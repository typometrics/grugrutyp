// The signed-in user, shared by every view that cares (header menu, saved queries,
// later the LLM features). One module-level ref rather than a store library: there is
// exactly one piece of cross-view state in this app.
import { ref } from 'vue'
import { auth } from './api'

export const user = ref(null)
export const authProviders = ref([])

export async function loadUser() {
  try {
    const [me, providers] = await Promise.all([auth.me(), auth.providers()])
    user.value = me.user
    authProviders.value = providers.providers
  } catch {
    // No session backend (old server, dev without API): the header simply shows no
    // sign-in button, which is the truthful rendering of the situation.
    user.value = null
    authProviders.value = []
  }
}

export async function logout() {
  await auth.logout()
  user.value = null
}
