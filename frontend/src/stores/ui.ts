import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUiStore = defineStore('ui', () => {
  const isLoginOpen = ref(false)
  const isRegisterOpen = ref(false)
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

  return {
    isLoginOpen,
    isRegisterOpen,
    isProfileOpen,
    isDeleteConfirmOpen,
    openLogin,
    openRegister,
    openDeleteConfirm,
    closeModal,
  }
})
