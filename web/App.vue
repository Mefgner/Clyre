<template>
  <v-app>
    <v-main>
      <router-view :key="$route.fullPath" />
    </v-main>
    <ModalContainer />
  </v-app>
</template>
