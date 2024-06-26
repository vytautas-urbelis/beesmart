import {configureStore} from '@reduxjs/toolkit'
import userCustomerReducer from './slices/userCustomerSlice.js';
import userEndUserReducer from './slices/userEndUserSlice.js';
import campaignReducer from './slices/campaignSlice.js';
import collectorReducer from './slices/collectorSlice.js';
import insightReducer from './slices/insightSlice.js';


export default configureStore({
    reducer: {
        customer: userCustomerReducer,
        endUser: userEndUserReducer,
        campaign: campaignReducer,
        collector: collectorReducer,
        insight: insightReducer,
    },
},)
