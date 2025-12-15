import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUiStore = defineStore('ui', () => {
  const isLoginOpen = ref(false)
  const loginError = ref('')
  const isRegisterOpen = ref(false)
  const registerError = ref('')
  const isProfileOpen = ref(false)
  const isDeleteConfirmOpen = ref(false)

  function openLogin () {
    isLoginOpen.value = true
    isRegisterOpen.value = false
  }

  function openRegister () {
    isRegisterOpen.value = true
    isLoginOpen.value = false
  }

  function openDeleteConfirm () {
    isDeleteConfirmOpen.value = true
  }

  function closeModal () {
    isLoginOpen.value = false
    isRegisterOpen.value = false
    isDeleteConfirmOpen.value = false
  }

  function clearErrors () {
    loginError.value = ''
    registerError.value = ''
  }

  return {
    isLoginOpen,
    loginError,
    isRegisterOpen,
    registerError,
    isProfileOpen,
    isDeleteConfirmOpen,
    openLogin,
    openRegister,
    openDeleteConfirm,
    closeModal,
    clearErrors,
  }
})
